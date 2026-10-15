from dataclasses import replace

import httpx
import pytest

from backend.app import notes
from backend.app.config import get_settings
from backend.app.db import Usage, session


def test_zero_budget_blocks_request(database, monkeypatch):
    settings = replace(get_settings(), qwen_key="test-placeholder", input_price=1, output_price=2)
    monkeypatch.setattr(notes, "get_settings", lambda: settings)
    with pytest.raises(notes.NotesError, match="预算不足"):
        notes.reserve("fake-job", "fake-model", 100, 100)


def test_pending_reservations_block_overspend(database, monkeypatch):
    settings = replace(
        get_settings(),
        qwen_key="test-placeholder",
        input_price=100,
        output_price=100,
        budget_cny=0.025,
    )
    monkeypatch.setattr(notes, "get_settings", lambda: settings)
    identifier = notes.reserve("fake-job", "fake-model", 100, 100)
    with pytest.raises(notes.NotesError, match="预算不足"):
        notes.reserve("fake-job2", "fake-model", 100, 100)
    notes.settle(identifier)
    with session() as db:
        assert db.get(Usage, identifier).billing_state == "unknown"
        assert notes.budget_summary(db)["remaining_cny"] == 0.005


def test_usage_settlement_counts_all_calls(database, monkeypatch):
    settings = replace(
        get_settings(), qwen_key="test-placeholder", input_price=1, output_price=2, budget_cny=1
    )
    monkeypatch.setattr(notes, "get_settings", lambda: settings)
    identifier = notes.reserve("fake-job", "fake-model", 100, 100)
    notes.settle(identifier, {"prompt_tokens": 20, "completion_tokens": 10})
    with session() as db:
        assert db.get(Usage, identifier).actual_cny == 0.00004


def test_cloud_timeout_keeps_reservation(database, monkeypatch):
    settings = replace(
        get_settings(), qwen_key="test-placeholder", input_price=1, output_price=2, budget_cny=1
    )
    monkeypatch.setattr(notes, "get_settings", lambda: settings)

    def fail(*args, **kwargs):
        raise httpx.ReadTimeout("simulated")

    monkeypatch.setattr(httpx.Client, "post", fail)
    with pytest.raises(notes.NotesError, match="用量待核对"):
        notes.cloud_call("fake-job", {"segments": []})
    with session() as db:
        assert notes.budget_summary(db)["unknown_calls"] == 1
