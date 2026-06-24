"""Researcher sub-agent: a Foundry agent that researches one focused topic via Grounding with Bing.

``run_researcher`` runs one researcher on a standalone topic. Grounding with Bing is a *managed*
tool baked into the agent definition; the function tools ``think_tool`` and ``searches_remaining``
are dispatched locally. Concurrency is capped by a semaphore honouring ``MAX_PARALLEL_RESEARCHERS``.
It never raises: a failure (e.g. throttling) returns ``ok=False`` so the lead keeps going and the
report can disclose the gap rather than failing the whole run.
"""

from __future__ import annotations

import asyncio
import logging
from functools import lru_cache

from deep_research.config import get_settings
from deep_research.observability import span
from deep_research.runtime import resolve_agent_id, run_agent
from deep_research.schemas import ResearchResult
from deep_research.tools import RESEARCHER_DISPATCH

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _semaphore() -> asyncio.Semaphore:
    return asyncio.Semaphore(get_settings().max_parallel_researchers)


async def run_researcher(topic: str) -> ResearchResult:
    """Run one researcher agent on ``topic`` and return its findings (never raises)."""
    cfg = get_settings()
    with span(f"researcher:{topic[:60]}", **{"research.topic": topic}):
        try:
            agent_id = await resolve_agent_id(cfg.researcher_agent_name)
            async with _semaphore():
                result = await run_agent(
                    agent_id,
                    topic,
                    dispatch=RESEARCHER_DISPATCH,
                    max_completion_tokens=cfg.researcher_max_completion_tokens or None,
                )
            return ResearchResult(topic=topic, summary=result.text, sources=result.sources, ok=True)
        except Exception as exc:  # noqa: BLE001 - degrade gracefully on throttling/timeouts
            logger.warning("Researcher failed for topic %r: %s", topic, exc)
            return ResearchResult(
                topic=topic,
                summary=(
                    "(This sub-topic could not be researched due to a temporary error such as "
                    "model rate limits. Proceed with the other findings.)"
                ),
                ok=False,
            )
