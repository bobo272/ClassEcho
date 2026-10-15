import sys
from copy import deepcopy
from types import ModuleType, SimpleNamespace

import pytest

from backend.app import asr
from backend.app.exports import transcript_srt


@pytest.mark.parametrize(
    "original, expected",
    [
        (
            "這段課堂筆記包含 API、Python 3.11 和 42 個例子。",
            "这段课堂笔记包含 API、Python 3.11 和 42 个例子。",
        ),
        ("简体笔记与 HTTP 200 不变。", "简体笔记与 HTTP 200 不变。"),
        ("HTTP 200 / Python 3.11 / 1.5ms", "HTTP 200 / Python 3.11 / 1.5ms"),
    ],
)
def test_script_conversion_preserves_raw_text_and_timing(original, expected):
    raw = [{"start": 1.25, "end": 2.5, "text": original}]
    before = deepcopy(raw)
    segments = asr.build_segments(raw, 3)
    assert raw == before
    assert segments == [
        {
            "id": "segment_00001",
            "start_ms": 1250,
            "end_ms": 2500,
            "raw_text": original,
            "text": expected,
        }
    ]


def test_asr_adapter_returns_simplified_subtitles_with_original_evidence(monkeypatch, tmp_path):
    # Keep CI independent of MLX/GPU; exercise the real conversion and export path.
    mlx = ModuleType("mlx")
    core = ModuleType("mlx.core")
    core.get_peak_memory = lambda: 0
    mlx.core = core
    monkeypatch.setitem(sys.modules, "mlx", mlx)
    monkeypatch.setitem(sys.modules, "mlx.core", core)
    monkeypatch.setitem(
        sys.modules,
        "mlx_whisper",
        SimpleNamespace(
            transcribe=lambda *args, **kwargs: {
                "segments": [{"start": 0, "end": 1, "text": "課堂筆記保留原始時間。"}]
            }
        ),
    )
    monkeypatch.setattr(asr, "model_ready", lambda name: True)
    segments, metrics = asr.transcribe(tmp_path / "unused.wav", 1, "small")
    assert metrics["text_normalization"] == "opencc:t2s"
    assert segments[0]["raw_text"] == "課堂筆記保留原始時間。"
    subtitles = transcript_srt({"segments": segments})
    assert "课堂笔记保留原始时间。" in subtitles
    assert "00:00:00,000 --> 00:00:01,000" in subtitles
