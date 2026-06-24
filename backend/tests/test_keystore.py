"""Env key store: validation + per-key daily cap (the cost guard)."""

from __future__ import annotations

from deep_research import keystore
from deep_research.config import get_settings


async def test_disabled_when_no_keys(monkeypatch):
    monkeypatch.setenv("API_KEYS", "")
    get_settings.cache_clear()
    keystore.reset_store()
    assert keystore.auth_enabled() is False
    assert await keystore.validate_key(None) == "anonymous"


async def test_validate_and_daily_cap(monkeypatch):
    key = "super-secret"
    monkeypatch.setenv("API_KEYS", f"Alice:{keystore.hash_key(key)}")
    monkeypatch.setenv("MAX_RUNS_PER_KEY_PER_DAY", "2")
    get_settings.cache_clear()
    keystore.reset_store()

    assert keystore.auth_enabled() is True
    assert await keystore.validate_key(key) == "Alice"
    assert await keystore.validate_key("wrong") is None

    ok1, name1, _ = await keystore.consume_run(key)
    ok2, _, _ = await keystore.consume_run(key)
    ok3, _, msg3 = await keystore.consume_run(key)
    assert ok1 and name1 == "Alice"
    assert ok2 is True
    assert ok3 is False and "limit" in msg3.lower()
