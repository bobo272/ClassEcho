import json
from copy import deepcopy

import httpx
import pytest

from backend.app import jobs, notes
from backend.app.notes_api import APIInput, save_api_config


def configure():
    return save_api_config(
        APIInput(
            base_url="https://relay.example.invalid/v1",
            model="test-model",
            api_key="test-only-fake-key",
        )
    )


def content_for(segments):
    return {
        "title": "事务",
        "sections": [
            {
                "heading": "原子性",
                "items": [
                    {
                        "kind": "course_content",
                        "text": "事务保持原子性。",
                        "source_segment_ids": [segments[0]["id"]],
                    }
                ],
            }
        ],
    }


def test_chunks_preserve_coverage_and_small_boundary_context():
    segments = [
        {"id": f"s{i}", "text": "字" * size} for i, size in enumerate([6500, 400, 300, 1700])
    ]
    original = deepcopy(segments)
    chunks = notes.split_api_segments(segments)
    assert len(chunks) == 2
    assert chunks[1][:2] == segments[1:3]
    assert {s["id"] for chunk in chunks for s in chunk} == {s["id"] for s in segments}
    assert all(sum(len(s["text"]) for s in chunk) <= notes.API_CHUNK_CHARS for chunk in chunks)
    assert segments == original


def test_failed_second_chunk_resumes_without_repeating_first_request(
    client, transcribed, monkeypatch
):
    config = configure()
    revised = client.patch(
        f"/api/lectures/{transcribed['id']}/transcript",
        json={
            "base_version_id": transcribed["transcript"]["id"],
            "edits": {"segment_00001": "甲" * 5000, "segment_00002": "乙" * 5000},
        },
    ).json()
    requests = []

    def handle(request):
        payload = json.loads(json.loads(request.content)["messages"][1]["content"])
        requests.append(payload["segments"])
        if len(requests) == 2:
            raise httpx.ReadTimeout("test timeout", request=request)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": json.dumps(content_for(payload["segments"]))},
                    }
                ]
            },
        )

    real_client = httpx.Client
    monkeypatch.setattr(
        notes.httpx,
        "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handle), **kwargs),
    )
    job = client.post(
        f"/api/lectures/{transcribed['id']}/notes",
        json={
            "transcript_id": revised["id"],
            "provider": "api",
            "consent": True,
            "api_revision": config.revision,
        },
    ).json()
    jobs.execute_job(job["id"])
    failed = client.get(f"/api/jobs/{job['id']}").json()
    assert failed["state"] == "failed"
    assert failed["checkpoint"]["notes_progress"] == {"completed": 1, "total": 2}
    assert len(failed["checkpoint"]["notes_chunks"]) == 1
    assert client.get(f"/api/lectures/{transcribed['id']}/notes").json() == []
    assert client.post(f"/api/jobs/{job['id']}/retry").status_code == 202
    jobs.execute_job(job["id"])
    finished = client.get(f"/api/jobs/{job['id']}").json()
    assert finished["state"] == "succeeded"
    assert finished["checkpoint"]["notes_progress"] == {"completed": 2, "total": 2}
    assert [chunk[0]["id"] for chunk in requests] == [
        "segment_00001",
        "segment_00002",
        "segment_00002",
    ]
    saved = client.get(f"/api/lectures/{transcribed['id']}/notes").json()[0]
    assert saved["prompt_version"] == notes.API_PROMPT_VERSION
    assert saved["content"]["sections"][0]["items"][0]["source_segment_ids"] == [
        "segment_00001",
        "segment_00002",
    ]


def test_configuration_change_between_chunks_stops_before_next_request(database, monkeypatch):
    config = configure()
    calls, checkpoint = [], {}

    def call(config, title, segments):
        calls.append(segments)
        configure()
        return content_for(segments)

    monkeypatch.setattr(notes, "call_api_chunk", call)
    with pytest.raises(notes.NotesError, match="设置已变更"):
        notes.api_note(
            "课程",
            [{"id": "a", "text": "甲" * 5000}, {"id": "b", "text": "乙" * 5000}],
            config.revision,
            checkpoint,
        )
    assert len(calls) == 1
    assert checkpoint["notes_progress"] == {"completed": 1, "total": 2}


def test_checkpoint_is_not_reused_for_different_source_text(database, monkeypatch):
    config = configure()
    calls, checkpoint = [], {}

    def call(config, title, segments):
        calls.append(segments)
        return content_for(segments)

    monkeypatch.setattr(notes, "call_api_chunk", call)
    notes.api_note("课程", [{"id": "a", "text": "旧文字"}], config.revision, checkpoint)
    notes.api_note("课程", [{"id": "a", "text": "新文字"}], config.revision, checkpoint)
    assert len(calls) == 2
    assert calls[1][0]["text"] == "新文字"


def test_merge_preserves_distinct_items_and_does_not_change_checkpoints():
    a = content_for([{"id": "a"}])
    b = content_for([{"id": "b"}])
    b["sections"][0]["items"].append(
        {"kind": "example", "text": "另一例子", "source_segment_ids": ["b"]}
    )
    original = deepcopy([a, b])
    result = notes.merge_api_chunks([a, b], [{"id": "a"}, {"id": "b"}])
    assert len(result["sections"]) == 1
    assert len(result["sections"][0]["items"]) == 2
    assert result["sections"][0]["items"][0]["source_segment_ids"] == ["a", "b"]
    assert [a, b] == original


@pytest.mark.parametrize("segments", [[], [{"id": "a", "text": "甲" * 8001}]])
def test_empty_or_oversized_single_segment_is_rejected(segments):
    with pytest.raises(notes.NotesError):
        notes.split_api_segments(segments)
