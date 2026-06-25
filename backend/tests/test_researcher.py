"""Researcher: throttle-aware retries + real-error capture on failure."""

from __future__ import annotations

from deep_research import researcher
from deep_research.config import get_settings
from deep_research.runtime import AgentResult


def _patch(monkeypatch, run_agent_impl):
    async def fake_resolve(name):
        return "agent-id"

    async def fast_sleep(_seconds):
        return None

    monkeypatch.setattr(researcher, "resolve_agent_id", fake_resolve)
    monkeypatch.setattr(researcher.asyncio, "sleep", fast_sleep)
    monkeypatch.setattr(researcher, "run_agent", run_agent_impl)


async def test_retries_throttle_then_succeeds(monkeypatch):
    monkeypatch.setenv("RESEARCHER_MAX_RETRIES", "3")
    get_settings.cache_clear()
    calls = {"n": 0}

    async def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("429 Too Many Requests: rate limit exceeded")
        return AgentResult(text="findings", sources=["http://x"])

    _patch(monkeypatch, flaky)
    result = await researcher.run_researcher("topic")
    assert result.ok is True
    assert calls["n"] == 3  # two throttles retried, third succeeds


async def test_non_throttle_not_retried_and_error_captured(monkeypatch):
    monkeypatch.setenv("RESEARCHER_MAX_RETRIES", "3")
    get_settings.cache_clear()
    calls = {"n": 0}

    async def boom(*a, **k):
        calls["n"] += 1
        raise ValueError("schema rejected")

    _patch(monkeypatch, boom)
    result = await researcher.run_researcher("topic")
    assert result.ok is False
    assert calls["n"] == 1  # non-throttle errors are not retried
    assert "ValueError" in result.error and "schema rejected" in result.error


async def test_throttle_exhausts_and_reports_error(monkeypatch):
    monkeypatch.setenv("RESEARCHER_MAX_RETRIES", "2")
    get_settings.cache_clear()
    calls = {"n": 0}

    async def always_throttle(*a, **k):
        calls["n"] += 1
        raise RuntimeError("throttled: 429")

    _patch(monkeypatch, always_throttle)
    result = await researcher.run_researcher("topic")
    assert result.ok is False
    assert calls["n"] == 3  # initial try + 2 retries
    assert "429" in result.error
