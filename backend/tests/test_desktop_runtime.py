from dataclasses import replace

import pytest

from backend.app import main
from backend.app.config import get_settings
from desktop.runtime import available_ports


def test_desktop_origin_matches_configured_port(client, monkeypatch):
    settings = replace(get_settings(), api_port=19283)
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    response = client.post(
        "/api/courses", json={"name": "桌面课"}, headers={"Origin": "http://127.0.0.1:19283"}
    )
    assert response.status_code == 201
    for origin in ["http://evil.example:19283", "http://127.0.0.1:19284", "http://127.0.0.1:8765"]:
        assert (
            client.post(
                "/api/courses", json={"name": "拒绝"}, headers={"Origin": origin}
            ).status_code
            == 403
        )


def test_health_identifies_owned_desktop_instance(client, monkeypatch):
    monkeypatch.setenv("CLASSECHO_INSTANCE_ID", "test-instance")
    monkeypatch.setattr(
        main.jobs, "connection", lambda: type("Redis", (), {"ping": lambda self: True})()
    )
    assert client.get("/api/health").json() == {
        "status": "ok",
        "redis": True,
        "instance_id": "test-instance",
    }


def test_desktop_ports_are_distinct_and_do_not_change_development_defaults():
    api, redis = available_ports()
    assert 0 < api <= 65535 and 0 < redis <= 65535 and api != redis


def test_invalid_desktop_port_is_rejected(monkeypatch):
    monkeypatch.setenv("CLASSECHO_API_PORT", "70000")
    get_settings.cache_clear()
    try:
        with pytest.raises(ValueError, match="端口"):
            get_settings()
    finally:
        get_settings.cache_clear()
