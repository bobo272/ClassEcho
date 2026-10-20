import fcntl
from datetime import UTC, datetime

from redis import Redis
from rq import Queue
from rq.exceptions import NoSuchJobError
from rq.job import Job as RQJob
from sqlalchemy import select, text

from . import asr
from .config import get_settings
from .db import Job, Lecture, Note, Transcript, Usage, new_id, now, session
from .media import media_dir, normalize
from .notes import API_PROMPT_VERSION, NotesError, api_note, extractive_note, qwen_note

QUEUE = "classecho"


def connection():
    return Redis.from_url(get_settings().redis_url, socket_connect_timeout=2, socket_timeout=3)


def queue():
    return Queue(QUEUE, connection=connection(), serializer="json")


def rq_id(job):
    return f"classecho-{job.id}-{job.attempt}"


def dispatch(job_id):
    with session() as db:
        job = db.get(Job, job_id)
        try:
            queue().enqueue(
                "backend.app.jobs.execute_job",
                job_id,
                job_id=rq_id(job),
                job_timeout=7200,
                result_ttl=86400,
                failure_ttl=86400,
                description=f"ClassEcho {job.kind}",
            )
        except Exception:
            job.state, job.error = "failed", "任务队列不可用，请启动 Redis 和 worker 后重试"
            job.updated_at = now()
            db.commit()


def create_job(lecture_id, kind, parameters, force=False):
    with session() as db:
        db.execute(text("BEGIN IMMEDIATE"))
        existing = db.scalars(
            select(Job)
            .where(Job.lecture_id == lecture_id, Job.kind == kind)
            .order_by(Job.created_at.desc())
        ).all()
        for previous in existing:
            if previous.state in ("queued", "running"):
                if previous.parameters != parameters:
                    raise ValueError("已有不同配置的同类任务正在处理，请先等待或取消排队")
                return previous.id
            if not force and previous.parameters == parameters and previous.state == "succeeded":
                return previous.id
        job = Job(id=new_id(), lecture_id=lecture_id, kind=kind, parameters=parameters)
        db.add(job)
        db.commit()
        job_id = job.id
    dispatch(job_id)
    return job_id


def stage(job_id, name, checkpoint=None):
    with session() as db:
        job = db.get(Job, job_id)
        job.stage, job.updated_at = name, now()
        if checkpoint is not None:
            job.checkpoint = checkpoint
        db.commit()


def reconcile(job_id):
    with session() as db:
        job = db.get(Job, job_id)
        if not job or job.state not in ("queued", "running"):
            return
        try:
            remote = RQJob.fetch(rq_id(job), connection=connection(), serializer="json")
            status = remote.get_status(refresh=True)
            heartbeat = remote.last_heartbeat
            abandoned = (
                status == "started"
                and heartbeat is not None
                and (datetime.now(UTC) - heartbeat).total_seconds() > 120
            )
            if status in ("failed", "stopped", "canceled", "finished") or abandoned:
                job.state = "failed"
                job.error = "任务进程中断或未保存完成结果，可重试；云端用量未知时先核对账单"
                job.updated_at = now()
                db.commit()
        except NoSuchJobError:
            # Only reconcile old missing jobs, avoiding the DB-commit/enqueue gap.
            age = (datetime.now(UTC) - datetime.fromisoformat(job.updated_at)).total_seconds()
            if age > 30:
                job.state, job.error = "failed", "任务队列中没有此任务，请启动 worker 后重试"
                job.updated_at = now()
                db.commit()
        except Exception:
            pass  # A temporary Redis outage does not erase a durable task.


def retry_job(job_id):
    reconcile(job_id)
    with session() as db:
        db.execute(text("BEGIN IMMEDIATE"))
        job = db.get(Job, job_id)
        if job is None or job.state != "failed":
            raise ValueError("只有失败任务可以重试")
        unsettled = db.scalar(
            select(Usage).where(
                Usage.job_id == job_id, Usage.billing_state.in_(["reserved", "unknown"])
            )
        )
        if unsettled:
            raise ValueError("此任务有待核对的云端调用；保留费用预留，禁止直接重试")
        if db.scalar(
            select(Job).where(
                Job.lecture_id == job.lecture_id, Job.state.in_(["queued", "running"])
            )
        ):
            raise ValueError("该录音已有正在处理的任务")
        job.state, job.error, job.updated_at = "queued", None, now()
        job.attempt += 1
        db.commit()
    dispatch(job_id)


def cancel_job(job_id):
    with session() as db:
        db.execute(text("BEGIN IMMEDIATE"))
        job = db.get(Job, job_id)
        if job is None or job.state != "queued":
            raise ValueError("只能取消尚未开始的任务；正在处理的任务请等待结束")
        try:
            RQJob.fetch(rq_id(job), connection=connection(), serializer="json").cancel()
        except Exception:
            pass  # Durable cancellation also makes a later dequeued invocation a no-op.
        job.state, job.stage, job.updated_at = "cancelled", "cancelled", now()
        db.commit()


def execute_job(job_id):
    with session() as db:
        db.execute(text("BEGIN IMMEDIATE"))
        job = db.get(Job, job_id)
        if job is None or job.state != "queued":
            return
        job.state, job.updated_at = "running", now()
        db.commit()
        lecture = db.get(Lecture, job.lecture_id)
        parameters, checkpoint = job.parameters, dict(job.checkpoint)
        kind = job.kind
    try:
        if kind == "transcribe":
            directory = media_dir(lecture.id)
            with (get_settings().data_dir / ".asr.lock").open("a") as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise ValueError("已有本地转录正在运行，请稍后重试") from None
                normalized = directory / "normalized.wav"
                if not checkpoint.get("normalized") or not normalized.exists():
                    stage(job_id, "normalize")
                    duration = normalize(
                        directory / ("original" + lecture.media_suffix), normalized
                    )
                    if abs(duration - lecture.duration) > 0.2:
                        raise ValueError("音轨规范化后时长发生变化，请核对原文件完整性")
                    checkpoint["normalized"] = True
                    stage(job_id, "normalize", checkpoint)
                stage(job_id, "download")
                asr.download_model(parameters["model"])
                stage(job_id, "transcribe")
                segments, metrics = asr.transcribe(
                    normalized,
                    lecture.duration,
                    parameters["model"],
                    parameters.get("initial_prompt", ""),
                )
                followup_id = None
                with session() as db:
                    transcript = Transcript(
                        id=new_id(),
                        lecture_id=lecture.id,
                        engine="mlx-whisper",
                        model=asr.MODELS[parameters["model"]]["repo"],
                        revision=asr.MODELS[parameters["model"]]["revision"],
                        segments=segments,
                        metrics=metrics,
                    )
                    db.add(transcript)
                    db.get(Lecture, lecture.id).active_transcript_id = transcript.id
                    job = db.get(Job, job_id)
                    job.state, job.stage, job.result_id, job.updated_at = (
                        "succeeded",
                        "complete",
                        transcript.id,
                        now(),
                    )
                    if options := parameters.get("after_transcribe"):
                        # Publish the transcript and the next durable task atomically:
                        # a browser refresh can never observe a completed chain with
                        # no follow-up task. Never send audio to the notes provider.
                        followup_id = new_id()
                        db.add(
                            Job(
                                id=followup_id,
                                lecture_id=lecture.id,
                                kind="notes",
                                parameters={**options, "transcript_id": transcript.id},
                            )
                        )
                    db.commit()
                if followup_id:
                    dispatch(followup_id)
        else:
            with session() as db:
                transcript = db.get(Transcript, parameters["transcript_id"])
                if not transcript or transcript.lecture_id != lecture.id:
                    raise ValueError("来源转录版本不存在")
                segments = transcript.segments
            stage(job_id, "draft")
            if parameters["provider"] == "extractive":
                content = extractive_note(lecture.title, segments)
                note_model = "local-extractive-v1"
            elif parameters["provider"] == "api":
                content, note_model = api_note(
                    lecture.title,
                    segments,
                    parameters.get("api_revision", ""),
                    checkpoint,
                    lambda saved: stage(job_id, "draft", saved),
                )
            elif parameters["provider"] == "qwen":
                content = qwen_note(job_id, lecture.title, segments)
                note_model = get_settings().qwen_model
            else:
                raise NotesError("未知笔记方式")
            stage(job_id, "validate")
            with session() as db:
                note = Note(
                    id=new_id(),
                    lecture_id=lecture.id,
                    transcript_id=parameters["transcript_id"],
                    provider=parameters["provider"],
                    model=note_model,
                    prompt_version=API_PROMPT_VERSION if parameters["provider"] == "api" else "v1",
                    content=content,
                )
                db.add(note)
                job = db.get(Job, job_id)
                job.state, job.stage, job.result_id, job.updated_at = (
                    "succeeded",
                    "complete",
                    note.id,
                    now(),
                )
                db.commit()
    except Exception as error:
        with session() as db:
            job = db.get(Job, job_id)
            if job:
                job.state, job.updated_at = "failed", now()
                job.error = (
                    str(error)
                    if isinstance(error, (ValueError, NotesError))
                    else "处理失败，请检查依赖、模型下载或本机资源后重试"
                )
                # Never expose an arbitrary upstream response, credential, or classroom text.
                if get_settings().qwen_key:
                    job.error = job.error.replace(get_settings().qwen_key, "[REDACTED]")
                job.error = job.error[:500]
                db.commit()
