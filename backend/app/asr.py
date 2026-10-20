import json
import os
import resource
import time
from functools import lru_cache
from pathlib import Path

from opencc import OpenCC

from .config import get_settings
from .schemas import validate_segments

MODELS = {
    "small": {
        "repo": "mlx-community/whisper-small-mlx",
        "revision": "45f3915923c7a79a5a5b5a7d909d39aeb0e5630e",
    },
    "turbo": {
        "repo": "mlx-community/whisper-large-v3-turbo",
        "revision": "a4aaeec0636e6fef84abdcbe3544cb2bf7e9f6fb",
    },
}


def model_directory(name):
    if name not in MODELS:
        raise ValueError("不支持的转录模型")
    return get_settings().data_dir / "models" / name / MODELS[name]["revision"]


def model_ready(name):
    directory = model_directory(name)
    return (
        (directory / "config.json").is_file()
        and any((directory / weight).is_file() for weight in ("weights.npz", "weights.safetensors"))
        and (directory / ".ready").is_file()
    )


def download_model(name):
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "120")
    from huggingface_hub import snapshot_download

    directory = model_directory(name)
    if not model_ready(name):
        snapshot_download(
            repo_id=MODELS[name]["repo"],
            revision=MODELS[name]["revision"],
            local_dir=directory,
            allow_patterns=["config.json", "weights.npz", "weights.safetensors", "README.md"],
            token=False,
        )
        (directory / ".ready").write_text(json.dumps(MODELS[name]))
    return directory


@lru_cache(maxsize=1)
def chinese_converter():
    return OpenCC("t2s.json")


def build_segments(raw_segments, duration):
    segments = []
    for raw in raw_segments:
        text = raw["text"].strip()
        start_ms = max(0, round(raw["start"] * 1000))
        end_ms = min(round(duration * 1000), round(raw["end"] * 1000))
        if text and end_ms > start_ms:
            segments.append(
                {
                    "id": f"segment_{len(segments) + 1:05d}",
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "raw_text": text,
                    "text": chinese_converter().convert(text),
                }
            )
    if not segments:
        raise ValueError("未识别出有效语音，请确认录音音量与内容")
    validate_segments(segments, duration)
    return segments


def transcribe(path: Path, duration, model_name, initial_prompt=""):
    import mlx.core as mx
    import mlx_whisper

    if not model_ready(model_name):
        raise ValueError("模型尚未下载完成")
    start = time.perf_counter()
    result = mlx_whisper.transcribe(
        str(path),
        path_or_hf_repo=str(model_directory(model_name)),
        language="zh",
        task="transcribe",
        initial_prompt=initial_prompt or None,
        verbose=None,
        temperature=0.0,
        condition_on_previous_text=False,
    )
    segments = build_segments(result["segments"], duration)
    elapsed = time.perf_counter() - start
    return segments, {
        "elapsed_seconds": round(elapsed, 3),
        "rtf": round(elapsed / duration, 4),
        "process_peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "mlx_peak_bytes": mx.get_peak_memory(),
        "text_normalization": "opencc:t2s",
    }
