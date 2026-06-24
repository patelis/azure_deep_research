"""Report writer: a Sources section is guaranteed; incomplete tasks get a completeness note."""

from __future__ import annotations

from deep_research import report
from deep_research.runtime import AgentResult
from deep_research.schemas import LeadSynthesis, TaskFinding


def _patch(monkeypatch, text: str):
    async def fake_resolve(name):
        return "agent-id"

    async def fake_run_agent(agent_id, content, **kw):
        return AgentResult(text=text, sources=[])

    monkeypatch.setattr(report, "resolve_agent_id", fake_resolve)
    monkeypatch.setattr(report, "run_agent", fake_run_agent)


async def test_sources_section_appended(monkeypatch):
    _patch(monkeypatch, "# Title\n\nSome body without a sources section.")
    syn = LeadSynthesis(
        objective="o",
        findings=[TaskFinding(task="t", summary="s", ok=True)],
        sources=["http://a", "http://b"],
    )
    res = await report.write_report(syn)
    assert "### Sources" in res.markdown
    assert "http://a" in res.markdown and "http://b" in res.markdown


async def test_completeness_note_when_incomplete(monkeypatch):
    _patch(monkeypatch, "# Title\n\nBody.\n\n### Sources\n1. http://a\n")
    syn = LeadSynthesis(
        objective="o",
        findings=[TaskFinding(task="failed topic", summary="n/a", ok=False)],
        sources=["http://a"],
    )
    res = await report.write_report(syn)
    assert "Completeness note" in res.markdown
    assert "failed topic" in res.markdown
