import pytest

from backend.app.schemas import validate_note, validate_segments


@pytest.mark.parametrize(
    "segment",
    [
        {"id": "s", "start_ms": 1000, "end_ms": 1000, "raw_text": "", "text": ""},
        {"id": "s", "start_ms": 0, "end_ms": 3000, "raw_text": "", "text": ""},
    ],
)
def test_invalid_timeline(segment):
    with pytest.raises(ValueError):
        validate_segments([segment], 2)


def test_nonexistent_reference_rejected():
    with pytest.raises(ValueError):
        validate_note(
            {
                "title": "无效引用",
                "sections": [
                    {
                        "heading": "标题",
                        "items": [{"text": "内容", "source_segment_ids": ["invented"]}],
                    }
                ],
            },
            [],
        )
