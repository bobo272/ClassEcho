import io
import wave

from backend.app import asr, live_asr


def preview(client, wav_bytes, offset=10000):
    return client.post(
        "/api/live-transcriptions",
        data={"offset_ms": str(offset)},
        files={"file": ("preview.wav", wav_bytes, "audio/wav")},
    )


def test_live_preview_queues_and_offsets_timestamps(client, wav_bytes, monkeypatch):
    queued = []
    monkeypatch.setattr(live_asr, "enqueue", queued.append)
    monkeypatch.setattr(asr, "model_ready", lambda model: True)
    monkeypatch.setattr(
        asr,
        "transcribe",
        lambda *args: (
            [
                {
                    "id": "segment_00001",
                    "start_ms": 200,
                    "end_ms": 900,
                    "text": "测试",
                    "raw_text": "測試",
                }
            ],
            {},
        ),
    )
    response = preview(client, wav_bytes)
    assert response.status_code == 202
    identifier = response.json()["id"]
    assert queued == [identifier]
    live_asr.execute_preview(identifier)
    result = client.get(f"/api/live-transcriptions/{identifier}").json()
    assert result["state"] == "succeeded"
    assert result["segments"][0]["start_ms"] == 10200
    assert result["segments"][0]["end_ms"] == 10900
    assert not (live_asr.directory(identifier) / "audio.wav").exists()
    # Repeated workers must not infer twice.
    monkeypatch.setattr(asr, "transcribe", lambda *args: (_ for _ in ()).throw(AssertionError()))
    live_asr.execute_preview(identifier)
    assert client.get(f"/api/live-transcriptions/{identifier}").json()["state"] == "succeeded"


def test_live_preview_rejects_invalid_audio_and_missing_model(client, wav_bytes, monkeypatch):
    monkeypatch.setattr(asr, "model_ready", lambda model: False)
    assert preview(client, wav_bytes).status_code == 409
    assert preview(client, b"broken").status_code == 400
    assert preview(client, b"x" * (live_asr.MAX_BYTES + 1)).status_code == 413
    assert preview(client, wav_bytes, -1).status_code == 422
    assert preview(client, wav_bytes, 5400000).status_code == 400
    data = io.BytesIO()
    with wave.open(data, "wb") as audio:
        audio.setnchannels(2)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b"\0" * 8)
    assert preview(client, data.getvalue()).status_code == 400


def test_live_preview_silence_failure_and_backpressure(client, wav_bytes, monkeypatch):
    monkeypatch.setattr(live_asr, "enqueue", lambda identifier: None)
    monkeypatch.setattr(asr, "model_ready", lambda model: True)
    first = preview(client, wav_bytes).json()["id"]
    preview(client, wav_bytes)
    assert preview(client, wav_bytes).status_code == 429

    def silence(*args):
        raise ValueError("未识别出有效语音，请确认录音音量与内容")

    monkeypatch.setattr(asr, "transcribe", silence)
    live_asr.execute_preview(first)
    assert client.get(f"/api/live-transcriptions/{first}").json()["segments"] == []
    third = preview(client, wav_bytes).json()["id"]

    def failure(*args):
        raise RuntimeError("PRIVATE_TRANSCRIPT_OR_SECRET")

    monkeypatch.setattr(asr, "transcribe", failure)
    live_asr.execute_preview(third)
    result = client.get(f"/api/live-transcriptions/{third}").json()
    assert result["state"] == "failed"
    assert "PRIVATE" not in str(result)


def test_live_queue_failure_and_invalid_id(client, wav_bytes, monkeypatch):
    monkeypatch.setattr(asr, "model_ready", lambda model: True)

    def failure(identifier):
        raise ConnectionError()

    monkeypatch.setattr(live_asr, "enqueue", failure)
    assert preview(client, wav_bytes).status_code == 503
    assert not [path for path in live_asr.root().iterdir() if path.is_dir()]
    assert client.get("/api/live-transcriptions/not-an-id").status_code == 404


def test_live_preview_timeout_releases_admission_slot(client, wav_bytes, monkeypatch):
    monkeypatch.setattr(asr, "model_ready", lambda model: True)
    monkeypatch.setattr(live_asr, "enqueue", lambda identifier: None)
    value = preview(client, wav_bytes).json()
    path = live_asr.directory(value["id"])
    value["created"] -= 301
    live_asr.write_status(path, value)
    result = client.get(f"/api/live-transcriptions/{value['id']}").json()
    assert result["state"] == "failed"
    assert not (path / "audio.wav").exists()
