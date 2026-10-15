import hashlib
import json
import math
import subprocess
from pathlib import Path

from .config import get_settings

EXTENSIONS = {".mp3", ".m4a", ".wav", ".mp4"}


def media_dir(lecture_id: str):
    if len(lecture_id) != 32 or any(c not in "0123456789abcdef" for c in lecture_id):
        raise ValueError("无效材料 ID")
    return get_settings().data_dir / "media" / lecture_id


def run_media(command: list[str], timeout=120):
    try:
        return subprocess.run(command, check=True, capture_output=True, timeout=timeout)
    except FileNotFoundError:
        raise ValueError("未安装 FFmpeg/ffprobe，请先运行 brew install ffmpeg") from None
    except subprocess.TimeoutExpired:
        raise ValueError("音视频处理超时") from None
    except subprocess.CalledProcessError:
        raise ValueError("音视频文件无法解码或不完整") from None


def probe(path: Path):
    output = run_media(
        ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)]
    )
    try:
        content = json.loads(output.stdout)
        duration = float(content["format"]["duration"])
        audio = next(stream for stream in content["streams"] if stream["codec_type"] == "audio")
        if not math.isfinite(duration) or duration <= 0 or int(audio["channels"]) <= 0:
            raise ValueError
    except (KeyError, ValueError, StopIteration, TypeError):
        raise ValueError("文件没有有效音轨或无法读取时长") from None
    if duration > get_settings().max_duration:
        raise ValueError("录音超过 90 分钟，请先拆分")
    return duration


def normalize(source: Path, target: Path):
    temporary = target.with_suffix(".tmp.wav")
    try:
        run_media(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-xerror",
                "-y",
                "-i",
                str(source),
                "-map",
                "0:a:0",
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                str(temporary),
            ],
            timeout=600,
        )
        duration = probe(temporary)
        temporary.replace(target)
        return duration
    finally:
        temporary.unlink(missing_ok=True)


def file_hash(path: Path):
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
