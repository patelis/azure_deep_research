"""Clarifier — fully decoupled from research.

A stateless Azure OpenAI **Responses API** call (``responses.parse``) with a versioned markdown
prompt. Given the conversation so far it returns a ``ClarifierTurn``: either a focused clarifying
question, or a research plan presented for approval (``plan_ready=True``). The 3-turn cap is
enforced here in code; the input guardrail (Prompt Shields) screens the latest user message first.
"""

from __future__ import annotations

import logging

from deep_research.azure_client import get_async_azure_openai_client
from deep_research.config import get_settings
from deep_research.guardrails import check_prompt
from deep_research.observability import span
from deep_research.prompts import render
from deep_research.schemas import ClarifierTurn
from deep_research.tools import get_today_str

logger = logging.getLogger(__name__)

# A conversation turn: (role, content) where role is "user" or "assistant".
Turn = tuple[str, str]


async def _parse(system: str, history: list[Turn]) -> ClarifierTurn:
    """One ``responses.parse`` call: system prompt + the conversation, typed to ClarifierTurn."""
    cfg = get_settings()
    client = get_async_azure_openai_client()
    messages = [{"role": "system", "content": system}]
    messages += [{"role": role, "content": content} for role, content in history]
    parsed = await client.responses.parse(
        model=cfg.main_model, input=messages, text_format=ClarifierTurn
    )
    return parsed.output_parsed


async def clarify(history: list[Turn]) -> ClarifierTurn:
    """Run one clarifier turn over the conversation ``history``.

    ``history`` is the full conversation as ``(role, content)`` turns (the UI holds it). After
    ``MAX_CLARIFY_ROUNDS`` clarifying questions, a plan is forced regardless.
    """
    cfg = get_settings()

    # Guardrail: screen the most recent user message before any planning.
    latest_user = next((c for r, c in reversed(history) if r == "user"), "")
    if latest_user:
        verdict = await check_prompt(latest_user)
        if not verdict.allowed:
            return ClarifierTurn(message=verdict.reason, plan_ready=False, clarification_round=0)

    rounds_used = sum(1 for role, _ in history if role == "assistant")
    force_plan = rounds_used >= cfg.max_clarify_rounds
    system = render(
        "clarifier",
        date=get_today_str(),
        max_clarify_rounds=cfg.max_clarify_rounds,
        rounds_used=rounds_used,
        force_plan=str(force_plan).lower(),
    )

    with span("clarify", **{"clarify.rounds_used": rounds_used, "clarify.force_plan": force_plan}):
        turn = await _parse(system, history)
        # Enforce the cap in code, not just in the prompt.
        if force_plan and not turn.plan_ready:
            logger.info("Clarify cap reached; forcing a plan.")
            forced = system + (
                "\n\nIMPORTANT: The clarification limit has been reached. You MUST return "
                "plan_ready=true with a complete plan now. Do NOT ask another question."
            )
            turn = await _parse(forced, history)

    turn.clarification_round = rounds_used
    return turn
