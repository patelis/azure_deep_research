"""Lead orchestrator: the hard subagent ceiling is enforced in code, and `done` stops early."""

from __future__ import annotations

from deep_research import lead
from deep_research.config import get_settings
from deep_research.runtime import AgentResult
from deep_research.schemas import DelegationPlan, ResearchPlan, ResearchResult


def _patch_common(monkeypatch, counter):
    async def fake_resolve(name):
        return "agent-id"

    async def fake_run_researcher(topic):
        counter["n"] += 1
        return ResearchResult(topic=topic, summary="findings", sources=["http://x"], ok=True)

    monkeypatch.setattr(lead, "resolve_agent_id", fake_resolve)
    monkeypatch.setattr(lead, "run_researcher", fake_run_researcher)


async def test_hard_cap_enforced_in_code(monkeypatch):
    # Lead keeps asking for 3 subtasks and never says done; code must stop at the ceiling of 2.
    monkeypatch.setenv("MAX_SUBAGENTS_PER_RUN", "2")
    monkeypatch.setenv("SUBAGENTS_PER_ROUND", "3")
    monkeypatch.setenv("MAX_DELEGATION_ROUNDS", "5")
    get_settings.cache_clear()

    counter = {"n": 0}
    _patch_common(monkeypatch, counter)

    async def greedy(agent_id, content, response_format=None, **kw):
        d = DelegationPlan(reflection="more", subtasks=["a", "b", "c"], done=False)
        return AgentResult(text=d.model_dump_json())

    monkeypatch.setattr(lead, "run_agent", greedy)

    synthesis = await lead.run_lead(ResearchPlan(objective="o", tasks=["t1", "t2"]))
    assert counter["n"] == 2  # never exceeds MAX_SUBAGENTS_PER_RUN
    assert len(synthesis.findings) == 2
    assert synthesis.sources == ["http://x"]


async def test_done_stops_early(monkeypatch):
    monkeypatch.setenv("MAX_SUBAGENTS_PER_RUN", "5")
    monkeypatch.setenv("MAX_DELEGATION_ROUNDS", "5")
    get_settings.cache_clear()

    counter = {"n": 0}
    _patch_common(monkeypatch, counter)

    async def finished(agent_id, content, response_format=None, **kw):
        d = DelegationPlan(reflection="nothing to do", subtasks=[], done=True)
        return AgentResult(text=d.model_dump_json())

    monkeypatch.setattr(lead, "run_agent", finished)

    synthesis = await lead.run_lead(ResearchPlan(objective="o", tasks=["t1"]))
    assert counter["n"] == 0
    assert synthesis.findings == []
