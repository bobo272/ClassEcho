from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from rq.exceptions import NoSuchJobError

from backend.app import jobs
from backend.app.db import Usage, session

RECONCILE = jobs.reconcile


def test_cancelled_task_never_runs(client, lecture, monkeypatch):
    def missing(*args, **kwargs):
        raise NoSuchJobError

    monkeypatch.setattr(jobs.RQJob, "fetch", missing)
    job = client.post(f"/api/lectures/{lecture['id']}/transcribe", json={}).json()
    assert client.post(f"/api/jobs/{job['id']}/cancel").json()["state"] == "cancelled"
    jobs.execute_job(job["id"])
    assert client.get(f"/api/jobs/{job['id']}").json()["state"] == "cancelled"
    assert client.delete(f"/api/lectures/{lecture['id']}").status_code == 204


def test_stale_worker_heartbeat_is_recoverable(client, lecture, monkeypatch):
    job = client.post(f"/api/lectures/{lecture['id']}/transcribe", json={}).json()
    remote = SimpleNamespace(
        last_heartbeat=datetime.now(UTC) - timedelta(minutes=5),
        get_status=lambda **kwargs: "started",
    )
    monkeypatch.setattr(jobs.RQJob, "fetch", lambda *args, **kwargs: remote)
    RECONCILE(job["id"])
    assert client.get(f"/api/jobs/{job['id']}").json()["state"] == "failed"


def test_unknown_cost_blocks_retry(client, lecture, monkeypatch):
    from backend.app.db import Job

    job = client.post(f"/api/lectures/{lecture['id']}/transcribe", json={}).json()
    with session() as db:
        db.get(Job, job["id"]).state = "failed"
        db.add(
            Usage(job_id=job["id"], model="test-model", reserved_cny=0.1, billing_state="unknown")
        )
        db.commit()
    response = client.post(f"/api/jobs/{job['id']}/retry")
    assert response.status_code == 400
    assert "待核对" in response.json()["detail"]


def test_active_job_does_not_silently_use_another_model(client, lecture):
    first = client.post(f"/api/lectures/{lecture['id']}/transcribe", json={"model": "small"})
    assert first.status_code == 202
    assert (
        client.post(
            f"/api/lectures/{lecture['id']}/transcribe", json={"model": "turbo"}
        ).status_code
        == 400
    )
