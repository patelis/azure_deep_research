"""Schema construction + strict JSON-schema generation."""

from __future__ import annotations

from deep_research.runtime import pydantic_response_format
from deep_research.schemas import (
    ClarifierTurn,
    DelegationPlan,
    LeadSynthesis,
    ResearchPlan,
    TaskFinding,
)


def test_clarifier_turn_defaults():
    t = ClarifierTurn(message="hi", plan_ready=False)
    assert t.plan is None
    assert t.clarification_round == 0


def test_clarifier_turn_with_plan():
    t = ClarifierTurn(
        message="here", plan_ready=True, plan=ResearchPlan(objective="o", tasks=["a", "b"])
    )
    assert t.plan_ready and t.plan and t.plan.tasks == ["a", "b"]


def test_delegation_defaults():
    d = DelegationPlan(reflection="r", done=True)
    assert d.subtasks == []
    assert d.subagents_spawned == 0


def test_lead_synthesis():
    s = LeadSynthesis(
        objective="o",
        findings=[TaskFinding(task="t", summary="s", ok=False)],
        sources=["http://x"],
    )
    assert s.findings[0].ok is False


def test_strict_response_format():
    rf = pydantic_response_format(DelegationPlan)
    schema = rf.json_schema.schema
    # _strictify makes every object closed + all keys required.
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"].keys())
