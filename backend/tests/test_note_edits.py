from alembic import command
from alembic.config import Config

from backend.app import jobs
from backend.app.config import ROOT
from backend.app.migrate import migrate


def make_note(client, detail):
    job = client.post(
        f"/api/lectures/{detail['id']}/notes", json={"transcript_id": detail["transcript"]["id"]}
    ).json()
    jobs.execute_job(job["id"])
    return client.get(f"/api/lectures/{detail['id']}/notes").json()[0]


def test_body_edits_preserve_generated_evidence_and_export_current_text(client, transcribed):
    note = make_note(client, transcribed)
    path = f"/api/notes/{note['id']}"
    text = "已核对：事务保持原子性。"
    response = client.put(path, json={"edit_version": 0, "text_edits": {"0.0": text}})
    assert response.status_code == 200
    saved = response.json()
    assert saved["content"] == note["content"]
    assert saved["text_edits"] == {"0.0": text}
    assert saved["edit_version"] == 1
    # A separate supplement edit must not erase the body edit.
    response = client.put(path, json={"edit_version": 1, "markdown": "我的补充"})
    assert response.json()["text_edits"] == {"0.0": text}
    assert client.put(path, json={"edit_version": 0, "markdown": "过期"}).status_code == 409
    base = f"/api/lectures/{transcribed['id']}/export"
    markdown = client.get(base, params={"format": "markdown"}).text
    assert text + "（用户修订）" in markdown
    assert "00:00:00.000" in markdown and "我的补充" in markdown
    backup = client.get(base, params={"format": "json"}).json()["notes"][0]
    assert backup["content"] == note["content"]
    assert backup["text_edits"] == {"0.0": text}
    # Restoring the original removes the override, without changing the supplement.
    restored = client.put(path, json={"edit_version": 2, "text_edits": {"0.0": None}}).json()
    assert restored["text_edits"] == {}
    assert restored["user_markdown"] == "我的补充"


def test_invalid_body_patch_is_atomic(client, transcribed):
    note = make_note(client, transcribed)
    path = f"/api/notes/{note['id']}"
    response = client.put(
        path,
        json={
            "edit_version": 0,
            "markdown": "不应写入",
            "text_edits": {"0.0": "有效", "9.0": "不存在"},
        },
    )
    assert response.status_code == 400
    response = client.put(path, json={"edit_version": 0, "text_edits": {"0.0": "  "}})
    assert response.status_code == 422
    current = client.get(f"/api/lectures/{transcribed['id']}/notes").json()[0]
    assert current["edit_version"] == 0
    assert current["text_edits"] == {} and current["user_markdown"] is None


def test_regeneration_keeps_body_corrections_on_previous_note(client, transcribed):
    note = make_note(client, transcribed)
    client.put(
        f"/api/notes/{note['id']}", json={"edit_version": 0, "text_edits": {"0.0": "用户修订"}}
    )
    job = client.post(
        f"/api/lectures/{transcribed['id']}/notes",
        json={
            "transcript_id": transcribed["transcript"]["id"],
            "force": True,
        },
    ).json()
    jobs.execute_job(job["id"])
    notes = client.get(f"/api/lectures/{transcribed['id']}/notes").json()
    assert len(notes) == 2
    assert next(row for row in notes if row["id"] == note["id"])["text_edits"] == {
        "0.0": "用户修订"
    }
    assert next(row for row in notes if row["id"] != note["id"])["text_edits"] == {}


def test_upgrade_existing_notes_keeps_content_and_adds_empty_edits(client, transcribed):
    note = make_note(client, transcribed)
    config = Config(str(ROOT / "backend" / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "backend" / "migrations"))
    command.downgrade(config, "0001")
    migrate()
    current = client.get(f"/api/lectures/{transcribed['id']}/notes").json()[0]
    assert current["id"] == note["id"] and current["content"] == note["content"]
    assert current["text_edits"] == {}
