import uuid
from datetime import UTC, datetime
from functools import lru_cache

from sqlalchemy import JSON, ForeignKey, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .config import get_settings


def new_id():
    return uuid.uuid4().hex


def now():
    return datetime.now(UTC).isoformat()


class Base(DeclarativeBase):
    pass


class Course(Base):
    __tablename__ = "courses"
    id: Mapped[str] = mapped_column(primary_key=True, default=new_id)
    name: Mapped[str]
    description: Mapped[str] = mapped_column(default="")
    created_at: Mapped[str] = mapped_column(default=now)


class Lecture(Base):
    __tablename__ = "lectures"
    id: Mapped[str] = mapped_column(primary_key=True, default=new_id)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"), index=True)
    title: Mapped[str]
    filename: Mapped[str]
    sha256: Mapped[str]
    duration: Mapped[float]
    media_suffix: Mapped[str]
    active_transcript_id: Mapped[str | None]
    is_demo: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[str] = mapped_column(default=now)


class Transcript(Base):
    __tablename__ = "transcripts"
    id: Mapped[str] = mapped_column(primary_key=True, default=new_id)
    lecture_id: Mapped[str] = mapped_column(ForeignKey("lectures.id"), index=True)
    parent_id: Mapped[str | None]
    engine: Mapped[str]
    model: Mapped[str]
    revision: Mapped[str]
    segments: Mapped[list] = mapped_column(JSON)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(default=now)


class Note(Base):
    __tablename__ = "notes"
    id: Mapped[str] = mapped_column(primary_key=True, default=new_id)
    lecture_id: Mapped[str] = mapped_column(ForeignKey("lectures.id"), index=True)
    transcript_id: Mapped[str]
    provider: Mapped[str]
    model: Mapped[str]
    prompt_version: Mapped[str] = mapped_column(default="v1")
    content: Mapped[dict] = mapped_column(JSON)
    user_markdown: Mapped[str | None]
    edit_version: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[str] = mapped_column(default=now)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(primary_key=True, default=new_id)
    lecture_id: Mapped[str] = mapped_column(ForeignKey("lectures.id"), index=True)
    kind: Mapped[str]
    state: Mapped[str] = mapped_column(default="queued")
    stage: Mapped[str] = mapped_column(default="queued")
    attempt: Mapped[int] = mapped_column(default=1)
    parameters: Mapped[dict] = mapped_column(JSON)
    checkpoint: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None]
    result_id: Mapped[str | None]
    created_at: Mapped[str] = mapped_column(default=now)
    updated_at: Mapped[str] = mapped_column(default=now)


class Usage(Base):
    __tablename__ = "usage_records"
    id: Mapped[str] = mapped_column(primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(index=True)
    model: Mapped[str]
    input_tokens: Mapped[int] = mapped_column(default=0)
    output_tokens: Mapped[int] = mapped_column(default=0)
    reserved_cny: Mapped[float]
    actual_cny: Mapped[float | None]
    billing_state: Mapped[str] = mapped_column(default="reserved")
    created_at: Mapped[str] = mapped_column(default=now)


class Bookmark(Base):
    __tablename__ = "bookmarks"
    id: Mapped[str] = mapped_column(primary_key=True, default=new_id)
    lecture_id: Mapped[str] = mapped_column(ForeignKey("lectures.id"), index=True)
    position_ms: Mapped[int]
    question: Mapped[str]
    created_at: Mapped[str] = mapped_column(default=now)


@lru_cache
def engine():
    directory = get_settings().data_dir
    directory.mkdir(parents=True, exist_ok=True)
    db = create_engine(
        f"sqlite:///{directory / 'classecho.sqlite3'}",
        connect_args={"check_same_thread": False, "timeout": 10},
    )

    @event.listens_for(db, "connect")
    def pragmas(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")

    return db


def session():
    return sessionmaker(engine(), expire_on_commit=False)()


def row_dict(row):
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}
