import json

import httpx

from backend.app import jobs, notes

REAL_DISPATCH = jobs.dispatch


def start_chain(client, detail, options):
    return client.post(
        f"/api/lectures/{detail['id']}/transcribe",
        json={"force": True, "after_transcribe": options},
    )


def finish_asr(client, detail, options):
    response = start_chain(client, detail, options)
    assert response.status_code == 202
    parent = response.json()
    jobs.execute_job(parent["id"])
    latest = client.get(f"/api/lectures/{detail['id']}").json()
    assert client.get(f"/api/jobs/{parent['id']}").json()["state"] == "succeeded"
    followup = next(item for item in latest["jobs"] if item["kind"] == "notes")
    return parent, followup, latest


def configure(client):
    response = client.put(
        "/api/settings/notes-api",
        json={
            "base_url": "https://relay.example.invalid/v1",
            "model": "fake-model",
            "api_key": "test-only-fake-key",
        },
    )
    assert response.status_code == 200
    return response.json()


def test_recording_chain_persists_next_task_without_browser(client, transcribed, monkeypatch):
    dispatched = []
    monkeypatch.setattr(jobs, "dispatch", dispatched.append)
    parent, followup, latest = finish_asr(client, transcribed, {"provider": "extractive"})
    assert followup["state"] == "queued"
    assert dispatched == [parent["id"], followup["id"]]
    assert followup["parameters"]["transcript_id"] == latest["active_transcript_id"]
    jobs.execute_job(followup["id"])
    result = client.get(f"/api/lectures/{transcribed['id']}").json()
    assert result["notes"][0]["provider"] == "extractive"
    assert result["notes"][0]["transcript_id"] == latest["active_transcript_id"]
    jobs.execute_job(parent["id"])
    repeated = client.get(f"/api/lectures/{transcribed['id']}").json()
    assert len([job for job in repeated["jobs"] if job["kind"] == "notes"]) == 1


def test_recording_chain_requires_explicit_current_api_consent(client, transcribed):
    assert start_chain(client, transcribed, {"provider": "api"}).status_code == 400
    config = configure(client)
    assert (
        start_chain(
            client, transcribed, {"provider": "api", "api_revision": config["revision"]}
        ).status_code
        == 409
    )
    assert (
        start_chain(
            client, transcribed, {"provider": "api", "consent": True, "api_revision": "old"}
        ).status_code
        == 409
    )
    assert start_chain(client, transcribed, {"provider": "qwen"}).status_code == 422


def test_api_changed_during_recording_or_asr_blocks_automatic_send(
    client, transcribed, monkeypatch
):
    config = configure(client)
    _, followup, _ = finish_asr(
        client,
        transcribed,
        {"provider": "api", "consent": True, "api_revision": config["revision"]},
    )
    configure(client)  # A new revision must not inherit an earlier recording's consent.

    def unexpected(**kwargs):
        raise AssertionError("must not contact provider")

    monkeypatch.setattr(notes.httpx, "Client", unexpected)
    jobs.execute_job(followup["id"])
    result = client.get(f"/api/jobs/{followup['id']}").json()
    assert result["state"] == "failed"
    detail = client.get(f"/api/lectures/{transcribed['id']}").json()
    assert detail["transcript"] and not detail["notes"]


def test_recording_to_ai_notes_uses_confirmed_text_and_citations(client, transcribed, monkeypatch):
    config = configure(client)
    calls = []
    content = {
        "title": "事务",
        "sections": [
            {
                "heading": "原子性",
                "items": [
                    {
                        "kind": "course_content",
                        "text": "事务全部提交或全部回滚。",
                        "source_segment_ids": ["segment_00001", "segment_00002"],
                    }
                ],
            }
        ],
    }

    def handle(request):
        calls.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(content)}}]
            },
        )

    real_client = httpx.Client
    monkeypatch.setattr(
        notes.httpx,
        "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handle), **kwargs),
    )
    _, followup, _ = finish_asr(
        client,
        transcribed,
        {"provider": "api", "consent": True, "api_revision": config["revision"]},
    )
    jobs.execute_job(followup["id"])
    result = client.get(f"/api/lectures/{transcribed['id']}").json()
    assert result["notes"][0]["provider"] == "api"
    assert result["notes"][0]["content"]["sections"][0]["items"][0]["source_segment_ids"] == [
        "segment_00001",
        "segment_00002",
    ]
    assert len(calls) == 1
    assert calls[0]["model"] == "fake-model"
    assert "事务具有原子性" in str(calls[0])
    assert "audio" not in calls[0]


def test_followup_queue_failure_keeps_transcript_and_can_retry(client, transcribed, monkeypatch):
    response = start_chain(client, transcribed, {"provider": "extractive"})

    def unavailable():
        raise ConnectionError()

    monkeypatch.setattr(jobs, "queue", unavailable)
    monkeypatch.setattr(jobs, "dispatch", REAL_DISPATCH)
    jobs.execute_job(response.json()["id"])
    detail = client.get(f"/api/lectures/{transcribed['id']}").json()
    followup = next(job for job in detail["jobs"] if job["kind"] == "notes")
    assert followup["state"] == "failed" and detail["transcript"]
    monkeypatch.setattr(jobs, "dispatch", lambda identifier: None)
    assert client.post(f"/api/jobs/{followup['id']}/retry").status_code == 202
    jobs.execute_job(followup["id"])
    assert client.get(f"/api/lectures/{transcribed['id']}/notes").json()
