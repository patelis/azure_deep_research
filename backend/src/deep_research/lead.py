"""Lead orchestrator: a Foundry agent that delegates research via a bounded delegation schema.

The lead is re-invoked once per **round**. Each round it returns a ``DelegationPlan`` — a short
reflection plus 1..N standalone subtasks (or ``done=True``). Our code spawns one researcher
sub-agent per subtask **in parallel** (semaphore in ``researcher.py``), enforcing a hard global
ceiling (``MAX_SUBAGENTS_PER_RUN``) and a per-round cap (``SUBAGENTS_PER_ROUND``) that the model
cannot exceed — the count is tracked in code, not just self-reported. When the lead is done (or a
cap is hit) the gathered results are compacted into a ``LeadSynthesis`` for the report writer.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from deep_research.config import get_settings
from deep_research.observability import span
from deep_research.prompts import render
from deep_research.researcher import run_researcher
from deep_research.runtime import pydantic_response_format, resolve_agent_id, run_agent
from deep_research.schemas import (
    DelegationPlan,
    LeadSynthesis,
    ResearchPlan,
    ResearchResult,
    TaskFinding,
)
from deep_research.tools import get_today_str

logger = logging.getLogger(__name__)

Progress = Callable[[str], None]


def _extract_json(text: str) -> str:
    """Return the first balanced JSON object in ``text`` (tolerates surrounding prose)."""
    start = text.find("{")
    if start == -1:
        return text
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return text[start:]


def _format_results(results: list[ResearchResult]) -> str:
    """Render the findings gathered so far for the lead's next-round context."""
    if not results:
        return "(no research gathered yet)"
    blocks = []
    for i, r in enumerate(results, 1):
        status = "" if r.ok else " [INCOMPLETE]"
        blocks.append(f"--- FINDING {i}: {r.topic}{status} ---\n{r.summary}")
    return "\n\n".join(blocks)


def _note(progress: Progress | None, message: str) -> None:
    if progress is not None:
        try:
            progress(message)
        except Exception:  # noqa: BLE001 - progress reporting must never break a run
            logger.debug("progress callback failed", exc_info=True)


async def run_lead(plan: ResearchPlan, progress: Progress | None = None) -> LeadSynthesis:
    """Execute the approved plan via bounded delegation rounds; return a compacted synthesis."""
    cfg = get_settings()
    lead_id = await resolve_agent_id(cfg.lead_agent_name)
    response_format = pydantic_response_format(DelegationPlan)

    results: list[ResearchResult] = []
    spawned = 0

    with span("lead", **{"research.tasks": len(plan.tasks)}):
        for round_idx in range(cfg.max_delegation_rounds):
            remaining = cfg.max_subagents_per_run - spawned
            if remaining <= 0:
                break

            context = render(
                "lead_researcher_round",
                date=get_today_str(),
                objective=plan.objective,
                tasks="\n".join(f"- {t}" for t in plan.tasks),
                findings=_format_results(results),
                spawned=spawned,
                max_subagents=cfg.max_subagents_per_run,
                per_round=min(cfg.subagents_per_round, remaining),
                round_index=round_idx + 1,
                max_rounds=cfg.max_delegation_rounds,
            )

            with span(f"lead:round{round_idx + 1}", **{"lead.spawned": spawned}):
                result = await run_agent(lead_id, context, response_format=response_format)
                try:
                    decision = DelegationPlan.model_validate_json(_extract_json(result.text))
                except Exception as exc:  # noqa: BLE001 - tolerate a malformed round; finish
                    logger.warning("Lead returned unparseable delegation plan: %s", exc)
                    break

            _note(progress, decision.reflection)

            if decision.done or not decision.subtasks:
                break

            # Hard cap: code decides how many actually run, regardless of the model's request.
            take = decision.subtasks[
                : min(len(decision.subtasks), cfg.subagents_per_round, remaining)
            ]
            _note(progress, f"Delegating {len(take)} researcher(s): " + "; ".join(take))

            round_results = await asyncio.gather(*(run_researcher(t) for t in take))
            results.extend(round_results)
            spawned += len(take)

    _note(progress, f"Compacting findings from {spawned} researcher(s)…")
    return _compact(plan, results)


def _compact(plan: ResearchPlan, results: list[ResearchResult]) -> LeadSynthesis:
    """Aggregate researcher results into the in-context hand-off for the report writer."""
    sources: list[str] = []
    for r in results:
        for url in r.sources:
            if url not in sources:
                sources.append(url)
    findings = [TaskFinding(task=r.topic, summary=r.summary, ok=r.ok) for r in results]
    return LeadSynthesis(objective=plan.objective, findings=findings, sources=sources)
