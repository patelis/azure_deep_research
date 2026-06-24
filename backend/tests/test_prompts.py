"""Every prompt loads and renders with its declared variables."""

from __future__ import annotations

from deep_research.prompts import list_prompts, render

EXPECTED = {
    "clarifier",
    "lead_researcher",
    "lead_researcher_round",
    "research_agent",
    "report_writer",
    "final_report",
}


def test_all_expected_prompts_present():
    names = {p.name for p in list_prompts()}
    assert EXPECTED <= names


def test_all_prompts_render():
    for p in list_prompts():
        values = {v: "x" for v in p.variables}
        out = render(p.name, **values)
        assert isinstance(out, str) and out.strip()
