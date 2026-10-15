import json
import stat

import httpx
import pytest

from backend.app import jobs, notes
from backend.app.config import get_settings
from backend.app.notes_api import load_api_config

CONFIG = {
    "base_url": "https://relay.example.invalid/v1",
    "model": "test-classroom-model",
    "api_key": "test-only-fake-secret",
}


def configure(client, **changes):
    response = client.put("/api/settings/notes-api", json={**CONFIG, **changes})
    assert response.status_code == 200
    return response.json()


def test_config_is_private_and_survives_reload(client):
    config = configure(client)
    assert config["configured"] is True
    assert "api_key" not in config
    assert CONFIG["api_key"] not in client.get("/api/settings").text
    assert load_api_config().api_key.get_secret_value() == CONFIG["api_key"]
    path = get_settings().data_dir / "notes-api.json"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_url_normalization_and_key_is_not_carried_to_another_server(client):
    configure(client, base_url=CONFIG["base_url"] + "/chat/completions/")
    response = client.put(
        "/api/settings/notes-api", json={"base_url": CONFIG["base_url"], "model": "new-model"}
    )
    assert response.json()["key_configured"] is True
    assert load_api_config().api_key.get_secret_value() == CONFIG["api_key"]
    response = client.put(
        "/api/settings/notes-api",
        json={"base_url": "https://another.example.invalid/v1", "model": "new-model"},
    )
    assert response.json()["configured"] is False
    assert load_api_config().api_key is None


@pytest.mark.parametrize(
    "url",
    [
        "file:///tmp/secret",
        "https://user:secret@example.invalid/v1",
        "https://example.invalid/v1?key=secret",
        "https://example.invalid/v1#secret",
        "https://example.invalid:wrong/v1",
    ],
)
def test_invalid_settings_do_not_echo_secrets(client, url):
    response = client.put(
        "/api/settings/notes-api",
        json={**CONFIG, "base_url": url},
    )
    assert response.status_code == 400
    assert "secret" not in response.text


def test_invalid_key_does_not_appear_in_validation_error(client):
    response = client.put(
        "/api/settings/notes-api", json={**CONFIG, "api_key": "private invalid key"}
    )
    assert response.status_code == 400
    assert "private invalid key" not in response.text


def test_api_requires_current_config_confirmation(client, transcribed):
    path = f"/api/lectures/{transcribed['id']}/notes"
    body = {"transcript_id": transcribed["transcript"]["id"], "provider": "api"}
    assert client.post(path, json=body).status_code == 400
    config = configure(client)
    assert client.post(path, json={**body, "api_revision": config["revision"]}).status_code == 409
    assert (
        client.post(path, json={**body, "consent": True, "api_revision": "old"}).status_code == 409
    )


def test_custom_api_job_sends_only_current_text_and_keeps_citations(
    client, transcribed, monkeypatch
):
    config = configure(client)
    recorded = []
    content = {
        "title": "事务",
        "sections": [
            {
                "heading": "原子性",
                "items": [
                    {
                        "kind": "course_content",
                        "text": "事务要么全部提交，要么全部回滚。",
                        "source_segment_ids": ["segment_00001", "segment_00002"],
                    }
                ],
            }
        ],
    }

    def handle(request):
        recorded.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": json.dumps(content)},
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
    response = client.post(
        f"/api/lectures/{transcribed['id']}/notes",
        json={
            "transcript_id": transcribed["transcript"]["id"],
            "provider": "api",
            "consent": True,
            "api_revision": config["revision"],
        },
    )
    assert response.status_code == 202
    job = response.json()
    assert CONFIG["api_key"] not in response.text
    jobs.execute_job(job["id"])
    assert client.get(f"/api/jobs/{job['id']}").json()["state"] == "succeeded"
    assert len(recorded) == 1
    request = recorded[0]
    assert str(request.url) == CONFIG["base_url"] + "/chat/completions"
    assert request.headers["Authorization"] == "Bearer " + CONFIG["api_key"]
    body = json.loads(request.content)
    assert body["model"] == CONFIG["model"]
    assert "enable_thinking" not in body and "response_format" not in body
    assert json.loads(body["messages"][1]["content"])["segments"] == [
        {"id": s["id"], "text": s["text"]} for s in transcribed["transcript"]["segments"]
    ]
    saved = client.get(f"/api/lectures/{transcribed['id']}/notes").json()[0]
    assert saved["content"] == content
    assert saved["model"] == CONFIG["model"] and saved["provider"] == "api"
    assert (
        client.get(f"/api/lectures/{transcribed['id']}/export?format=markdown").status_code == 200
    )


@pytest.mark.parametrize("failure", ["timeout", "redirect", "invalid_reference", "truncated"])
def test_api_failures_do_not_retry_or_save_invalid_notes(client, transcribed, monkeypatch, failure):
    config = configure(client)
    calls = []

    def handle(request):
        calls.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout(CONFIG["api_key"], request=request)
        if failure == "redirect":
            return httpx.Response(302, headers={"Location": "https://other.example.invalid"})
        content = {
            "title": "标题",
            "sections": [
                {
                    "heading": "主题",
                    "items": [
                        {
                            "text": "合并解释",
                            "source_segment_ids": ["invented"],
                        }
                    ],
                }
            ],
        }
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "length" if failure == "truncated" else "stop",
                        "message": {"content": json.dumps(content)},
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
            "transcript_id": transcribed["transcript"]["id"],
            "provider": "api",
            "consent": True,
            "api_revision": config["revision"],
        },
    ).json()
    jobs.execute_job(job["id"])
    result = client.get(f"/api/jobs/{job['id']}")
    assert result.json()["state"] == "failed"
    assert CONFIG["api_key"] not in result.text
    assert len(calls) == 1
    assert client.get(f"/api/lectures/{transcribed['id']}/notes").json() == []


def test_queued_job_never_sends_to_changed_api(client, transcribed, monkeypatch):
    config = configure(client)
    job = client.post(
        f"/api/lectures/{transcribed['id']}/notes",
        json={
            "transcript_id": transcribed["transcript"]["id"],
            "provider": "api",
            "consent": True,
            "api_revision": config["revision"],
        },
    ).json()
    configure(client, base_url="https://another.example.invalid/v1")

    def forbidden(**kwargs):
        pytest.fail("A changed API configuration must not start a request")

    monkeypatch.setattr(notes.httpx, "Client", forbidden)
    jobs.execute_job(job["id"])
    result = client.get(f"/api/jobs/{job['id']}").json()
    assert result["state"] == "failed"
    assert "设置已变更" in result["error"]
