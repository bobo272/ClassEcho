import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CourseInput(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)

    @field_validator("name")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("课程名称不能为空")
        return value.strip()


class Segment(StrictModel):
    id: str = Field(min_length=1, max_length=80)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    raw_text: str = Field(max_length=20000)
    text: str = Field(max_length=20000)


def validate_segments(segments: list[dict], duration: float):
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("音频时长无效")
    seen = set()
    previous = -1
    for raw in segments:
        segment = Segment.model_validate(raw)
        if segment.id in seen:
            raise ValueError("转录片段 ID 重复")
        if (
            segment.start_ms < previous
            or segment.end_ms <= segment.start_ms
            or segment.end_ms > round(duration * 1000) + 100
        ):
            raise ValueError("转录片段时间范围无效")
        seen.add(segment.id)
        previous = segment.start_ms
    return segments


class TranscriptEdit(StrictModel):
    base_version_id: str
    edits: dict[str, str] = Field(min_length=1, max_length=10000)

    @field_validator("edits")
    @classmethod
    def text_size(cls, value):
        if (
            any(len(text) > 20000 for text in value.values())
            or sum(map(len, value.values())) > 500000
        ):
            raise ValueError("修订文本过长")
        return value


class TranscribeInput(StrictModel):
    model: Literal["small", "turbo"] = "small"
    initial_prompt: str = Field(default="", max_length=2000)
    force: bool = False


class NoteInput(StrictModel):
    transcript_id: str
    provider: Literal["extractive", "qwen", "api"] = "extractive"
    consent: bool = False
    api_revision: str = Field(default="", max_length=80)
    force: bool = False


class NoteItem(StrictModel):
    kind: Literal["course_content", "example", "task", "uncertain"] = "course_content"
    text: str = Field(min_length=1, max_length=5000)
    source_segment_ids: list[str] = Field(min_length=1, max_length=100)


class NoteSection(StrictModel):
    heading: str = Field(min_length=1, max_length=200)
    items: list[NoteItem] = Field(min_length=1, max_length=100)


class StructuredNote(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    sections: list[NoteSection] = Field(min_length=1, max_length=100)


def validate_note(content, segments):
    note = StructuredNote.model_validate(content)
    ids = {segment["id"] for segment in segments}
    for section in note.sections:
        for item in section.items:
            if any(source not in ids for source in item.source_segment_ids):
                raise ValueError("笔记引用了不存在的转录片段")
    return note.model_dump()


class NoteEdit(StrictModel):
    markdown: str = Field(max_length=300000)
    edit_version: int = Field(ge=0)


class BookmarkInput(StrictModel):
    position_ms: int = Field(ge=0)
    question: str = Field(min_length=1, max_length=2000)
