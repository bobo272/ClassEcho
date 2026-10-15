import io
import wave

import pytest
from fastapi.testclient import TestClient

from backend.app import jobs
from backend.app.config import get_settings
from backend.app.db import engine
from backend.app.migrate import migrate


@pytest.fixture
def database(tmp_path, monkeypatch):
    monkeypatch.setenv("CLASSECHO_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CLASSECHO_BUDGET_CNY", "0")
    monkeypatch.setenv("QWEN_API_KEY", "")
    get_settings.cache_clear()
    engine.cache_clear()
    migrate()
    yield
    engine().dispose()
    engine.cache_clear()
    get_settings.cache_clear()


@pytest.fixture
def client(database, monkeypatch):
    from backend.app.main import app

    monkeypatch.setattr(jobs, "dispatch", lambda identifier: None)
    monkeypatch.setattr(jobs, "reconcile", lambda identifier: None)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def wav_bytes():
    file = io.BytesIO()
    with wave.open(file, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(b"\0\0" * 32000)
    return file.getvalue()


@pytest.fixture
def lecture(client, wav_bytes):
    course = client.post("/api/courses", json={"name": "测试课程"}).json()
    response = client.post(
        f"/api/courses/{course['id']}/lectures",
        files={"file": ("test.wav", wav_bytes, "audio/wav")},
    )
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def transcribed(client, lecture, monkeypatch):
    from backend.app import asr

    monkeypatch.setattr(asr, "download_model", lambda name: None)
    monkeypatch.setattr(
        asr,
        "transcribe",
        lambda *args: (
            [
                {
                    "id": "segment_00001",
                    "start_ms": 0,
                    "end_ms": 900,
                    "raw_text": "事务具有原子性。",
                    "text": "事务具有原子性。",
                },
                {
                    "id": "segment_00002",
                    "start_ms": 1000,
                    "end_ms": 1900,
                    "raw_text": "要么全部提交，要么全部回滚。",
                    "text": "要么全部提交，要么全部回滚。",
                },
            ],
            {"elapsed_seconds": 0.01},
        ),
    )
    job = client.post(f"/api/lectures/{lecture['id']}/transcribe", json={}).json()
    jobs.execute_job(job["id"])
    assert client.get(f"/api/jobs/{job['id']}").json()["state"] == "succeeded"
    return client.get(f"/api/lectures/{lecture['id']}").json()
