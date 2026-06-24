"""Clarifier: questions under the cap, a forced plan once the cap is reached."""

from __future__ import annotations

from deep_research import clarifier
from deep_research.config import get_settings
from deep_research.schemas import ClarifierTurn, ResearchPlan


async def test_question_under_cap(monkeypatch):
    monkeypatch.setenv("MAX_CLARIFY_ROUNDS", "3")
    get_settings.cache_clear()

    async def fake_parse(system, history):
        return ClarifierTurn(message="Could you clarify the scope?", plan_ready=False)

    monkeypatch.setattr(clarifier, "_parse", fake_parse)
    turn = await clarifier.clarify([("user", "research EVs")])
    assert turn.plan_ready is False


async def test_plan_forced_after_cap(monkeypatch):
    monkeypatch.setenv("MAX_CLARIFY_ROUNDS", "2")
    get_settings.cache_clear()

    async def fake_parse(system, history):
        # The forced second pass appends an explicit instruction to the system prompt.
        if "MUST return plan_ready=true" in system:
            return ClarifierTurn(
                message="Here is the plan.",
                plan_ready=True,
                plan=ResearchPlan(objective="o", tasks=["t1"]),
            )
        return ClarifierTurn(message="another question?", plan_ready=False)

    monkeypatch.setattr(clarifier, "_parse", fake_parse)

    # Two assistant turns already => rounds_used == 2 == cap => force a plan.
    history = [
        ("user", "a"),
        ("assistant", "q1"),
        ("user", "b"),
        ("assistant", "q2"),
        ("user", "c"),
    ]
    turn = await clarifier.clarify(history)
    assert turn.plan_ready is True
    assert turn.plan is not None and turn.plan.tasks == ["t1"]
