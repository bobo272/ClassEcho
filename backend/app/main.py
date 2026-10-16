import hashlib
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import delete, select, text
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import asr, jobs
from .config import ROOT, get_settings
from .db import Bookmark, Course, Job, Lecture, Note, Transcript, Usage, new_id, row_dict, session
from .exports import backup_json, note_markdown, transcript_srt
from .live_asr import router as live_router
from .media import EXTENSIONS, media_dir, normalize, probe
from .migrate import migrate
from .notes import budget_summary
from .notes_api import APIInput, load_api_config, save_api_config
from .schemas import (
    BookmarkInput,
    CourseInput,
    NoteEdit,
    NoteInput,
    TranscribeInput,
    TranscriptEdit,
)


@asynccontextmanager
async def lifespan(app):
    migrate()
    yield


app = FastAPI(title="ClassEcho", version="0.1.0", lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])
app.include_router(live_router)


@app.middleware("http")
async def local_origin(request: Request, call_next):
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        if origin:
            parsed = urlsplit(origin)
            if (
                parsed.scheme != "http"
                or parsed.hostname not in ("localhost", "127.0.0.1")
                or parsed.port not in (5173, 8765)
            ):
                return JSONResponse({"detail": "拒绝来自其他网站的本机写入请求"}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.exception_handler(ValueError)
async def value_error(request, error):
    return JSONResponse({"detail": str(error)}, status_code=400)


def require(db, model, identifier):
    row = db.get(model, identifier)
    if row is None:
        raise HTTPException(404, "内容不存在")
    return row


@app.get("/api/health")
def health():
    try:
        jobs.connection().ping()
        available = True
    except Exception:
        available = False
    return {"status": "ok", "redis": available}


@app.get("/api/settings")
def settings_info():
    settings = get_settings()
    with session() as db:
        return {
            "qwen_configured": bool(settings.qwen_key),
            "qwen_model": settings.qwen_model,
            "prices_configured": settings.input_price is not None
            and settings.output_price is not None,
            "budget": budget_summary(db),
            "notes_api": load_api_config().public(),
            "models": [
                {"name": name, **value, "ready": asr.model_ready(name)}
                for name, value in asr.MODELS.items()
            ],
            "max_file_mb": 500,
            "max_minutes": 90,
        }


@app.put("/api/settings/notes-api")
async def update_notes_api(request: Request):
    try:
        body = APIInput.model_validate(await request.json())
    except ValueError:
        # Validation errors may contain input values, including a supplied secret.
        raise HTTPException(
            400, "请检查接口 URL、模型和密钥格式；URL 不可含凭据或查询参数"
        ) from None
    return save_api_config(body).public()


@app.get("/api/usage")
def usage():
    with session() as db:
        return {
            "summary": budget_summary(db),
            "records": [
                row_dict(record)
                for record in db.scalars(select(Usage).order_by(Usage.created_at.desc())).all()
            ],
        }


@app.post("/api/demo", status_code=201)
def demo():
    from .demo import create_demo

    return create_demo()


@app.get("/api/courses")
def courses():
    with session() as db:
        return [
            row_dict(course)
            for course in db.scalars(select(Course).order_by(Course.created_at)).all()
        ]


@app.post("/api/courses", status_code=201)
def create_course(body: CourseInput):
    with session() as db:
        course = Course(**body.model_dump())
        db.add(course)
        db.commit()
        return row_dict(course)


@app.get("/api/courses/{course_id}/lectures")
def lectures(course_id: str):
    with session() as db:
        require(db, Course, course_id)
        return [
            row_dict(lecture)
            for lecture in db.scalars(
                select(Lecture)
                .where(Lecture.course_id == course_id)
                .order_by(Lecture.created_at.desc())
            ).all()
        ]


@app.post("/api/courses/{course_id}/lectures", status_code=201)
async def import_lecture(course_id: str, file: Annotated[UploadFile, File()]):
    with session() as db:
        require(db, Course, course_id)
    filename = Path(file.filename or "录音").name
    suffix = Path(filename).suffix.lower()
    if suffix not in EXTENSIONS:
        raise HTTPException(400, "仅支持 MP3、M4A、WAV、MP4 和 WebM")
    identifier = new_id()
    directory = media_dir(identifier)
    directory.mkdir(parents=True)
    target = directory / ("original" + suffix)
    size, digest = 0, hashlib.sha256()
    try:
        with target.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > get_settings().max_upload_bytes:
                    raise HTTPException(413, "文件超过 500MB")
                digest.update(chunk)
                output.write(chunk)
        # MediaRecorder WebM often has no duration header; decode before measuring it.
        if suffix == ".webm":
            duration = await run_in_threadpool(normalize, target, directory / "normalized.wav")
        else:
            duration = await run_in_threadpool(probe, target)
        with session() as db:
            require(db, Course, course_id)
            lecture = Lecture(
                id=identifier,
                course_id=course_id,
                title=Path(filename).stem[:200],
                filename=filename[:255],
                sha256=digest.hexdigest(),
                duration=duration,
                media_suffix=suffix,
            )
            db.add(lecture)
            db.commit()
            return row_dict(lecture)
    except Exception:
        shutil.rmtree(directory, ignore_errors=True)
        raise
    finally:
        await file.close()


@app.get("/api/lectures/{lecture_id}")
def lecture_detail(lecture_id: str):
    with session() as db:
        lecture = require(db, Lecture, lecture_id)
        job_ids = list(
            db.scalars(
                select(Job.id).where(
                    Job.lecture_id == lecture_id, Job.state.in_(["queued", "running"])
                )
            )
        )
    for job_id in job_ids:
        jobs.reconcile(job_id)
    with session() as db:
        lecture = require(db, Lecture, lecture_id)
        transcripts = db.scalars(
            select(Transcript)
            .where(Transcript.lecture_id == lecture_id)
            .order_by(Transcript.created_at.desc())
        ).all()
        return {
            **row_dict(lecture),
            "transcript": row_dict(db.get(Transcript, lecture.active_transcript_id))
            if lecture.active_transcript_id
            else None,
            "transcript_versions": [
                {key: value for key, value in row_dict(t).items() if key != "segments"}
                for t in transcripts
            ],
            "notes": [
                row_dict(n)
                for n in db.scalars(
                    select(Note)
                    .where(Note.lecture_id == lecture_id)
                    .order_by(Note.created_at.desc())
                ).all()
            ],
            "jobs": [
                row_dict(j)
                for j in db.scalars(
                    select(Job).where(Job.lecture_id == lecture_id).order_by(Job.created_at.desc())
                ).all()
            ],
            "bookmarks": [
                row_dict(b)
                for b in db.scalars(
                    select(Bookmark)
                    .where(Bookmark.lecture_id == lecture_id)
                    .order_by(Bookmark.position_ms)
                ).all()
            ],
        }


@app.post("/api/lectures/{lecture_id}/transcribe", status_code=202)
def start_transcribe(lecture_id: str, body: TranscribeInput):
    with session() as db:
        require(db, Lecture, lecture_id)
    if body.after_transcribe and body.after_transcribe.provider == "api":
        config = load_api_config()
        if not config.configured:
            raise HTTPException(400, "请先在设置中填写 AI 接口 URL、模型和密钥")
        if (
            not body.after_transcribe.consent
            or body.after_transcribe.api_revision != config.revision
        ):
            raise HTTPException(409, "请核对当前 AI 接口设置，确认在录音结束后发送转录文本")
    identifier = jobs.create_job(
        lecture_id,
        "transcribe",
        body.model_dump(exclude={"force"}, exclude_none=True),
        force=body.force,
    )
    with session() as db:
        return row_dict(require(db, Job, identifier))


@app.get("/api/lectures/{lecture_id}/transcript")
def transcript(lecture_id: str, version_id: str | None = None):
    with session() as db:
        lecture = require(db, Lecture, lecture_id)
        result = require(db, Transcript, version_id or lecture.active_transcript_id or "")
        if result.lecture_id != lecture_id:
            raise HTTPException(404, "转录版本不存在")
        return row_dict(result)


@app.patch("/api/lectures/{lecture_id}/transcript")
def edit_transcript(lecture_id: str, body: TranscriptEdit):
    with session() as db:
        db.execute(text("BEGIN IMMEDIATE"))
        lecture = require(db, Lecture, lecture_id)
        if lecture.active_transcript_id != body.base_version_id:
            raise HTTPException(409, "转录已被修改，请刷新后重试")
        original = require(db, Transcript, body.base_version_id)
        if any(key not in {segment["id"] for segment in original.segments} for key in body.edits):
            raise HTTPException(400, "修订包含不存在的片段")
        segments = [
            {**segment, "text": body.edits.get(segment["id"], segment["text"])}
            for segment in original.segments
        ]
        revised = Transcript(
            id=new_id(),
            lecture_id=lecture_id,
            parent_id=original.id,
            engine=original.engine,
            model=original.model,
            revision=original.revision,
            segments=segments,
            metrics=original.metrics,
        )
        db.add(revised)
        lecture.active_transcript_id = revised.id
        db.commit()
        return row_dict(revised)


@app.post("/api/lectures/{lecture_id}/notes", status_code=202)
def start_notes(lecture_id: str, body: NoteInput):
    with session() as db:
        require(db, Lecture, lecture_id)
        source = require(db, Transcript, body.transcript_id)
        if source.lecture_id != lecture_id:
            raise HTTPException(400, "转录不属于当前录音")
        if body.provider == "qwen" and not body.consent:
            raise HTTPException(400, "请先确认将此转录版本发送给云模型")
        if body.provider == "api":
            config = load_api_config()
            if not config.configured:
                raise HTTPException(400, "请先在设置中填写 AI 接口 URL、模型和密钥")
            if not body.consent or body.api_revision != config.revision:
                raise HTTPException(409, "请核对当前 AI 接口设置，确认向该接口发送转录文本")
    identifier = jobs.create_job(
        lecture_id, "notes", body.model_dump(exclude={"force"}), force=body.force
    )
    with session() as db:
        return row_dict(require(db, Job, identifier))


@app.get("/api/lectures/{lecture_id}/notes")
def notes(lecture_id: str):
    with session() as db:
        require(db, Lecture, lecture_id)
        return [
            row_dict(row)
            for row in db.scalars(
                select(Note).where(Note.lecture_id == lecture_id).order_by(Note.created_at.desc())
            ).all()
        ]


@app.put("/api/notes/{note_id}")
def edit_note(note_id: str, body: NoteEdit):
    with session() as db:
        db.execute(text("BEGIN IMMEDIATE"))
        note = require(db, Note, note_id)
        if note.edit_version != body.edit_version:
            raise HTTPException(409, "笔记已在其他页面修改，请刷新后重试")
        if body.markdown is None and not body.text_edits:
            raise HTTPException(400, "没有需要保存的笔记修改")
        if body.text_edits:
            originals = {
                f"{section_index}.{item_index}": item["text"]
                for section_index, section in enumerate(note.content["sections"])
                for item_index, item in enumerate(section["items"])
            }
            if any(key not in originals for key in body.text_edits):
                raise HTTPException(400, "修改包含不存在的笔记条目")
            edits = dict(note.text_edits)
            for key, value in body.text_edits.items():
                if value is None or value == originals[key]:
                    edits.pop(key, None)
                else:
                    edits[key] = value
            note.text_edits = edits
        if body.markdown is not None:
            note.user_markdown = body.markdown
        note.edit_version += 1
        db.commit()
        return row_dict(note)


@app.get("/api/jobs/{job_id}")
def job_detail(job_id: str):
    jobs.reconcile(job_id)
    with session() as db:
        return row_dict(require(db, Job, job_id))


@app.post("/api/jobs/{job_id}/cancel")
def cancel(job_id: str):
    jobs.cancel_job(job_id)
    return job_detail(job_id)


@app.post("/api/jobs/{job_id}/retry", status_code=202)
def retry(job_id: str):
    jobs.retry_job(job_id)
    return job_detail(job_id)


@app.post("/api/lectures/{lecture_id}/bookmarks", status_code=201)
def add_bookmark(lecture_id: str, body: BookmarkInput):
    with session() as db:
        lecture = require(db, Lecture, lecture_id)
        if body.position_ms > lecture.duration * 1000:
            raise HTTPException(400, "标记时间超出录音范围")
        bookmark = Bookmark(lecture_id=lecture_id, **body.model_dump())
        db.add(bookmark)
        db.commit()
        return row_dict(bookmark)


@app.delete("/api/bookmarks/{bookmark_id}", status_code=204)
def remove_bookmark(bookmark_id: str):
    with session() as db:
        db.delete(require(db, Bookmark, bookmark_id))
        db.commit()


@app.get("/api/lectures/{lecture_id}/media")
def media(lecture_id: str):
    with session() as db:
        lecture = require(db, Lecture, lecture_id)
        target = media_dir(lecture_id) / ("original" + lecture.media_suffix)
        if not target.is_file():
            raise HTTPException(404, "原始媒体文件不存在")
        return FileResponse(target)


@app.get("/api/lectures/{lecture_id}/export")
def export(
    lecture_id: str,
    format: str = "markdown",
    note_id: str | None = None,
    version_id: str | None = None,
):
    with session() as db:
        lecture = require(db, Lecture, lecture_id)
        transcripts = [
            row_dict(t)
            for t in db.scalars(select(Transcript).where(Transcript.lecture_id == lecture_id))
        ]
        notes = [row_dict(n) for n in db.scalars(select(Note).where(Note.lecture_id == lecture_id))]
        if format == "json":
            bookmarks = [
                row_dict(b)
                for b in db.scalars(select(Bookmark).where(Bookmark.lecture_id == lecture_id))
            ]
            content, extension, mime = (
                backup_json(row_dict(lecture), transcripts, notes, bookmarks),
                "json",
                "application/json",
            )
        elif format == "srt":
            source = next(
                (t for t in transcripts if t["id"] == (version_id or lecture.active_transcript_id)),
                None,
            )
            if not source:
                raise HTTPException(404, "转录版本不存在")
            content, extension, mime = transcript_srt(source), "srt", "text/plain"
        elif format == "markdown":
            note = (
                next((n for n in notes if n["id"] == note_id), None)
                if note_id
                else max(notes, key=lambda n: n["created_at"], default=None)
            )
            if not note:
                raise HTTPException(404, "还没有笔记")
            source = next(t for t in transcripts if t["id"] == note["transcript_id"])
            content, extension, mime = note_markdown(note, source), "md", "text/markdown"
        else:
            raise HTTPException(400, "不支持的导出格式")
        return Response(
            content,
            media_type=mime,
            headers={
                "Content-Disposition": f'attachment; filename="classecho-{lecture_id[:8]}.{extension}"'
            },
        )


@app.delete("/api/lectures/{lecture_id}", status_code=204)
def delete_lecture(lecture_id: str):
    with session() as db:
        db.execute(text("BEGIN IMMEDIATE"))
        require(db, Lecture, lecture_id)
        if db.scalar(
            select(Job).where(Job.lecture_id == lecture_id, Job.state.in_(["queued", "running"]))
        ):
            raise HTTPException(409, "录音仍有任务在处理，请等待完成或失败后删除")
        for model in (Bookmark, Note, Transcript, Job):
            db.execute(delete(model).where(model.lecture_id == lecture_id))
        db.execute(delete(Lecture).where(Lecture.id == lecture_id))
        db.commit()
    directory = media_dir(lecture_id)
    if directory.exists():
        shutil.rmtree(directory, ignore_errors=False)


@app.get("/api/{path:path}")
def api_not_found(path: str):
    raise HTTPException(404, "接口不存在")


frontend = ROOT / "frontend" / "dist"
if frontend.is_dir():
    app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
