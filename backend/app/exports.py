import json


def timestamp(milliseconds: int, srt=False):
    seconds, ms = divmod(milliseconds, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    separator = "," if srt else "."
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}{separator}{ms:03d}"


def note_markdown(note, transcript):
    lines = [f"# {note['content']['title']}", "", f"来源转录版本：`{transcript['id']}`", ""]
    if note["provider"] in ("extractive", "demo"):
        lines += ["> 本地逐段摘录 / 预生成示例，未经云端 AI 整理。", ""]
    by_id = {segment["id"]: segment for segment in transcript["segments"]}
    for section_index, section in enumerate(note["content"]["sections"]):
        lines += [f"## {section['heading']}", ""]
        for item_index, item in enumerate(section["items"]):
            refs = " ".join(
                f"[{timestamp(by_id[source]['start_ms'])} · {source}]"
                for source in item["source_segment_ids"]
            )
            edited = note.get("text_edits", {}).get(f"{section_index}.{item_index}")
            label = "（用户修订）" if edited is not None else ""
            lines.append(f"- {edited if edited is not None else item['text']}{label} {refs}")
        lines.append("")
    if note.get("user_markdown") is not None:
        lines += ["## 用户笔记", "", note["user_markdown"], ""]
    return "\n".join(lines)


def transcript_srt(transcript):
    return (
        "\n\n".join(
            f"{index}\n{timestamp(segment['start_ms'], True)} --> {timestamp(segment['end_ms'], True)}\n{segment['text']}"
            for index, segment in enumerate(transcript["segments"], 1)
        )
        + "\n"
    )


def backup_json(lecture, transcripts, notes, bookmarks):
    public_lecture = {key: value for key, value in lecture.items() if key not in ("sha256",)}
    return json.dumps(
        {
            "format": "classecho-backup-v1",
            "lecture": public_lecture,
            "transcripts": transcripts,
            "notes": notes,
            "bookmarks": bookmarks,
        },
        ensure_ascii=False,
        indent=2,
    )
