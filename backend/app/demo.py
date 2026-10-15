import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from sqlalchemy import select

from .config import ROOT
from .db import Course, Lecture, Note, Transcript, new_id, session
from .media import file_hash, media_dir, probe, run_media


def create_demo():
    with session() as db:
        existing = db.scalar(select(Lecture).where(Lecture.is_demo.is_(True)))
        if existing and (media_dir(existing.id) / "original.wav").exists():
            return {"course_id": existing.course_id, "lecture_id": existing.id}
    manifest = json.loads((ROOT / "samples" / "demo.json").read_text())
    if not shutil.which("say"):
        raise ValueError("此示例使用 macOS say 合成语音，当前系统不可用；仍可导入自己的录音")
    identifier = new_id()
    directory = media_dir(identifier)
    directory.mkdir(parents=True)
    segments = []
    try:
        with tempfile.TemporaryDirectory(prefix="classecho-demo-") as temp:
            temp = Path(temp)
            elapsed = 0
            concat = []
            for index, item in enumerate(manifest["segments"]):
                source = temp / f"part{index}.aiff"
                target = temp / f"part{index}.wav"
                try:
                    subprocess.run(
                        ["say", "-v", "Tingting", "-r", "170", "-o", str(source), item["text"]],
                        check=True,
                        capture_output=True,
                        timeout=60,
                    )
                except (subprocess.SubprocessError, FileNotFoundError):
                    raise ValueError(
                        "演示语音生成失败，请检查 macOS 是否有 Tingting 中文语音"
                    ) from None
                run_media(
                    [
                        "ffmpeg",
                        "-nostdin",
                        "-v",
                        "error",
                        "-y",
                        "-i",
                        str(source),
                        "-ac",
                        "1",
                        "-ar",
                        "16000",
                        str(target),
                    ]
                )
                duration_ms = round(probe(target) * 1000)
                segments.append(
                    {
                        "id": f"segment_{index + 1:05d}",
                        "start_ms": elapsed,
                        "end_ms": elapsed + duration_ms,
                        "raw_text": item["text"],
                        "text": item["text"],
                    }
                )
                elapsed += duration_ms
                concat.append(f"file '{target.name}'")
            listing = temp / "parts.txt"
            listing.write_text("\n".join(concat))
            output = directory / "original.wav"
            run_media(
                [
                    "ffmpeg",
                    "-nostdin",
                    "-v",
                    "error",
                    "-y",
                    "-f",
                    "concat",
                    "-safe",
                    "1",
                    "-i",
                    str(listing),
                    "-c",
                    "copy",
                    str(output),
                ]
            )
        with session() as db:
            course = Course(id=new_id(), name="ClassEcho 示例课程", description=manifest["notice"])
            db.add(course)
            db.flush()
            transcript_id = new_id()
            lecture = Lecture(
                id=identifier,
                course_id=course.id,
                title=manifest["title"],
                filename="demo.wav",
                sha256=file_hash(output),
                duration=probe(output),
                media_suffix=".wav",
                active_transcript_id=transcript_id,
                is_demo=True,
            )
            db.add(lecture)
            db.flush()
            transcript = Transcript(
                id=transcript_id,
                lecture_id=identifier,
                engine="pre-generated-demo",
                model="macOS-say-Tingting",
                revision="demo-v1",
                segments=segments,
                metrics={},
            )
            db.add(transcript)
            db.add(
                Note(
                    lecture_id=identifier,
                    transcript_id=transcript_id,
                    provider="demo",
                    model="pre-generated-demo-v1",
                    content={
                        "title": manifest["title"],
                        "sections": [
                            {
                                "heading": item["heading"],
                                "items": [
                                    {
                                        "kind": "course_content",
                                        "text": item["text"],
                                        "source_segment_ids": [segments[index]["id"]],
                                    }
                                ],
                            }
                            for index, item in enumerate(manifest["segments"])
                        ],
                    },
                )
            )
            db.commit()
            return {"course_id": course.id, "lecture_id": identifier}
    except Exception:
        shutil.rmtree(directory, ignore_errors=True)
        raise
