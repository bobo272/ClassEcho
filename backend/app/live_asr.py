"""Short-lived local microphone previews; final recordings use the normal durable workflow."""

import fcntl
import io
import json
import shutil
import time
import wave
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from . import asr, jobs
from .config import get_settings
from .db import new_id

router = APIRouter(prefix="/api/live-transcriptions")
MAX_BYTES = 12 * 16000 * 2 + 44


def root():
    path = get_settings().data_dir / "live-previews"
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def directory(identifier):
    if len(identifier) != 32 or any(c not in "0123456789abcdef" for c in identifier):
        raise HTTPException(404, "实时转录不存在")
    return root() / identifier


def write_status(path: Path, value):
    temporary = path / "status.tmp"
    temporary.write_text(json.dumps(value, ensure_ascii=False))
    temporary.chmod(0o600)
    temporary.replace(path / "status.json")


def read_status(path: Path):
    try:
        value = json.loads((path / "status.json").read_text())
    except (OSError, ValueError):
        raise HTTPException(404, "实时转录已过期；完整录音仍可保存") from None
    if value["state"] in ("queued", "running") and time.time() - value["created"] > 300:
        # Requests expire in the queue after 120s and workers have a 120s timeout.
        value.update(state="failed", error="实时识别超时，请检查 worker；完整录音不受影响")
        write_status(path, value)
        (path / "audio.wav").unlink(missing_ok=True)
    return value


def enqueue(identifier):
    jobs.queue().enqueue(
        "backend.app.live_asr.execute_preview",
        identifier,
        job_id=f"classecho-preview-{identifier}",
        job_timeout=120,
        ttl=120,
        result_ttl=0,
        failure_ttl=0,
        description="ClassEcho live preview",
    )


@router.post("", status_code=202)
async def start_preview(
    file: Annotated[UploadFile, File()],
    model: Annotated[Literal["small", "turbo"], Form()] = "small",
    offset_ms: Annotated[int, Form(ge=0, le=5400000)] = 0,
):
    try:
        content = await file.read(MAX_BYTES + 1)
    finally:
        await file.close()
    if len(content) > MAX_BYTES:
        raise HTTPException(413, "实时音频分片超过 12 秒大小上限")
    try:
        with wave.open(io.BytesIO(content)) as audio:
            if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) != (1, 2, 16000):
                raise ValueError
            frames = audio.getnframes()
            if not 1 <= frames <= 12 * 16000 or len(audio.readframes(frames)) != frames * 2:
                raise ValueError
    except (wave.Error, EOFError, ValueError):
        raise HTTPException(400, "实时分片须为完整的 16kHz 单声道 PCM16 WAV") from None
    if offset_ms + frames / 16 > get_settings().max_duration * 1000:
        raise HTTPException(400, "实时分片超出录音时长上限")
    if not asr.model_ready(model):
        raise HTTPException(409, "本地模型尚未就绪；先下载模型，或在录音结束后转录")
    with (root() / ".queue.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        pending = 0
        for path in root().iterdir():
            if not path.is_dir() or len(path.name) != 32:
                continue
            try:
                state = read_status(path)
                if time.time() - state["created"] > 3600:
                    shutil.rmtree(path)
                elif state["state"] in ("queued", "running"):
                    pending += 1
            except HTTPException:
                continue
        if pending >= 2:
            raise HTTPException(429, "本地实时识别暂忙，稍后继续；完整录音不受影响")
        identifier = new_id()
        path = directory(identifier)
        path.mkdir(mode=0o700)
        audio_path = path / "audio.wav"
        audio_path.write_bytes(content)
        audio_path.chmod(0o600)
        value = {
            "id": identifier,
            "state": "queued",
            "created": time.time(),
            "model": model,
            "offset_ms": offset_ms,
            "duration": frames / 16000,
            "segments": [],
            "error": None,
        }
        write_status(path, value)
        try:
            enqueue(identifier)
        except Exception:
            shutil.rmtree(path, ignore_errors=True)
            raise HTTPException(503, "实时识别队列不可用；请启动 Redis 和 worker") from None
    return value


@router.get("/{identifier}")
def preview_status(identifier: str):
    return read_status(directory(identifier))


def execute_preview(identifier):
    path = directory(identifier)
    try:
        value = read_status(path)
    except HTTPException:
        return
    if value["state"] != "queued":
        return
    value["state"] = "running"
    write_status(path, value)
    try:
        with (get_settings().data_dir / ".asr.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError("本地转录暂忙；完整录音不受影响") from None
            if not asr.model_ready(value["model"]):
                raise ValueError("本地模型尚未就绪")
            try:
                segments, _ = asr.transcribe(path / "audio.wav", value["duration"], value["model"])
            except ValueError as error:
                if str(error) != "未识别出有效语音，请确认录音音量与内容":
                    raise
                segments = []
            value["segments"] = [
                {
                    **item,
                    "id": f"{identifier}-{item['id']}",
                    "start_ms": item["start_ms"] + value["offset_ms"],
                    "end_ms": item["end_ms"] + value["offset_ms"],
                }
                for item in segments
            ]
            value["state"] = "succeeded"
    except Exception:
        # Do not persist arbitrary model exceptions or upstream/private content.
        value.update(
            state="failed", error="本地实时识别未完成，请检查模型或任务队列；完整录音不受影响"
        )
    finally:
        (path / "audio.wav").unlink(missing_ok=True)
        write_status(path, value)
