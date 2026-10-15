from dataclasses import replace

from sqlalchemy import select

from backend.app import jobs
from backend.app.config import get_settings
from backend.app.db import Job, Usage, session
from backend.app.media import media_dir

REAL_DISPATCH = jobs.dispatch
REAL_RECONCILE = jobs.reconcile


def note_for(client, detail):
    job = client.post(
        f"/api/lectures/{detail['id']}/notes", json={"transcript_id": detail["transcript"]["id"]}
    ).json()
    jobs.execute_job(job["id"])
    return client.get(f"/api/lectures/{detail['id']}/notes").json()[0]


def test_real_media_import_and_range(client, lecture, wav_bytes):
    response = client.get(f"/api/lectures/{lecture['id']}/media", headers={"Range": "bytes=0-15"})
    assert response.status_code == 206
    assert response.content == wav_bytes[:16]
    assert response.headers["content-range"].startswith("bytes 0-15/")


def test_bad_media_leaves_no_directory(client):
    course = client.post("/api/courses", json={"name": "坏文件课程"}).json()
    response = client.post(
        f"/api/courses/{course['id']}/lectures",
        files={"file": ("../../secret.wav", b"broken", "audio/wav")},
    )
    assert response.status_code == 400
    assert not list((get_settings().data_dir / "media").iterdir())


def test_upload_limit(client, lecture, wav_bytes, monkeypatch):
    from backend.app import main

    settings = replace(get_settings(), max_upload_bytes=8)
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    response = client.post(
        f"/api/courses/{lecture['course_id']}/lectures", files={"file": ("large.wav", wav_bytes)}
    )
    assert response.status_code == 413


def test_transcript_snapshot_preserves_original_and_rejects_stale(client, transcribed):
    base = transcribed["transcript"]
    url = f"/api/lectures/{transcribed['id']}/transcript"
    payload = {
        "base_version_id": base["id"],
        "edits": {"segment_00001": "事务具有原子性（核对后修订）。"},
    }
    response = client.patch(url, json=payload)
    assert response.status_code == 200
    revised = response.json()
    assert revised["id"] != base["id"]
    assert revised["segments"][0]["raw_text"] == base["segments"][0]["raw_text"]
    assert client.get(url, params={"version_id": base["id"]}).json() == base
    assert client.patch(url, json=payload).status_code == 409


def test_notes_references_edits_and_exports(client, transcribed):
    note = note_for(client, transcribed)
    assert note["provider"] == "extractive"
    saved = client.put(
        f"/api/notes/{note['id']}",
        json={"markdown": "我的理解：保持全部成功或全部失败。", "edit_version": 0},
    )
    assert saved.status_code == 200
    assert (
        client.put(
            f"/api/notes/{note['id']}", json={"markdown": "过期修改", "edit_version": 0}
        ).status_code
        == 409
    )
    base = f"/api/lectures/{transcribed['id']}/export"
    markdown = client.get(base, params={"format": "markdown"}).text
    assert "00:00:00.000" in markdown and "我的理解" in markdown and "未经云端 AI 整理" in markdown
    srt = client.get(base, params={"format": "srt"}).text
    assert "00:00:01,000 --> 00:00:01,900" in srt
    backup = client.get(base, params={"format": "json"}).json()
    assert backup["format"] == "classecho-backup-v1"
    assert "raw_text" in backup["transcripts"][0]["segments"][0]
    assert "QWEN_API_KEY" not in str(backup)


def test_new_note_does_not_overwrite_user_edits(client, transcribed):
    first = note_for(client, transcribed)
    client.put(f"/api/notes/{first['id']}", json={"markdown": "必须保留", "edit_version": 0})
    response = client.patch(
        f"/api/lectures/{transcribed['id']}/transcript",
        json={
            "base_version_id": transcribed["transcript"]["id"],
            "edits": {"segment_00001": "新的修订"},
        },
    )
    transcribed["transcript"] = response.json()
    note_for(client, transcribed)
    notes = client.get(f"/api/lectures/{transcribed['id']}/notes").json()
    assert len(notes) == 2
    assert next(note for note in notes if note["id"] == first["id"])["user_markdown"] == "必须保留"


def test_cloud_requires_consent(client, transcribed):
    response = client.post(
        f"/api/lectures/{transcribed['id']}/notes",
        json={"transcript_id": transcribed["transcript"]["id"], "provider": "qwen"},
    )
    assert response.status_code == 400


def test_same_request_is_idempotent(client, transcribed):
    first = client.post(f"/api/lectures/{transcribed['id']}/transcribe", json={}).json()
    second = client.post(f"/api/lectures/{transcribed['id']}/transcribe", json={}).json()
    assert first["id"] == second["id"]
    with session() as db:
        assert len(db.scalars(select(Job)).all()) == 1


def test_normalization_checkpoint_survives_failed_asr(client, lecture, monkeypatch):
    from backend.app import asr

    real_normalize = jobs.normalize
    calls = []
    monkeypatch.setattr(
        jobs, "normalize", lambda *args: (calls.append(1), real_normalize(*args))[1]
    )
    monkeypatch.setattr(asr, "download_model", lambda name: None)

    def failed(*args):
        raise ValueError("模拟模型失败")

    monkeypatch.setattr(asr, "transcribe", failed)
    job = client.post(f"/api/lectures/{lecture['id']}/transcribe", json={}).json()
    jobs.execute_job(job["id"])
    assert client.get(f"/api/jobs/{job['id']}").json()["checkpoint"]["normalized"]
    assert client.post(f"/api/jobs/{job['id']}/retry").status_code == 202
    jobs.execute_job(job["id"])
    assert len(calls) == 1


def test_queue_unavailable_is_visible(client, lecture, monkeypatch):
    monkeypatch.setattr(jobs, "dispatch", REAL_DISPATCH)
    monkeypatch.setattr(jobs, "queue", lambda: (_ for _ in ()).throw(ConnectionError()))
    response = client.post(f"/api/lectures/{lecture['id']}/transcribe", json={})
    assert response.json()["state"] == "failed"
    assert "任务队列不可用" in response.json()["error"]


def test_delete_cleans_media_but_preserves_spending(client, transcribed):
    note_for(client, transcribed)
    with session() as db:
        db.add(
            Usage(
                job_id="historical",
                model="mock",
                reserved_cny=0.01,
                actual_cny=0.01,
                billing_state="estimated",
            )
        )
        db.commit()
    path = media_dir(transcribed["id"])
    assert path.exists()
    assert client.delete(f"/api/lectures/{transcribed['id']}").status_code == 204
    assert not path.exists()
    assert client.get(f"/api/lectures/{transcribed['id']}").status_code == 404
    assert client.get("/api/usage").json()["summary"]["committed_cny"] == 0.01


def test_bookmark_bounds(client, lecture):
    url = f"/api/lectures/{lecture['id']}/bookmarks"
    assert client.post(url, json={"position_ms": 5000, "question": "超出范围"}).status_code == 400
    response = client.post(url, json={"position_ms": 1000, "question": "这里没听懂"})
    assert response.status_code == 201
    assert client.delete(f"/api/bookmarks/{response.json()['id']}").status_code == 204


def test_cross_origin_mutation_is_rejected(client):
    assert (
        client.post(
            "/api/courses", json={"name": "bad"}, headers={"Origin": "https://example.com"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/courses", json={"name": "ok"}, headers={"Origin": "http://127.0.0.1:5173"}
        ).status_code
        == 201
    )
