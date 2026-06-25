"""Researcher sub-agent: a Foundry agent that researches one focused topic via Grounding with Bing.

``run_researcher`` runs one researcher on a standalone topic. Grounding with Bing is a *managed*
tool baked into the agent definition; the function tools ``think_tool`` and ``searches_remaining``
are dispatched locally. Concurrency is capped by a semaphore honouring ``MAX_PARALLEL_RESEARCHERS``.

It never raises. On a **throttle** (429 / rate limit) the run is retried with exponential backoff
(``RESEARCHER_MAX_RETRIES`` / ``RESEARCHER_RETRY_BASE_SECONDS``); on any final failure it returns
``ok=False`` with the real error captured in ``ResearchResult.error`` (also set as a span
attribute) so the lead keeps going and the report can disclose the actual cause.
"""

from __future__ import annotations

import asyncio
import logging
import random
from functools import lru_cache

from deep_research.config import get_settings
from deep_research.observability import span
from deep_research.runtime import resolve_agent_id, run_agent
from deep_research.schemas import ResearchResult
from deep_research.tools import RESEARCHER_DISPATCH

logger = logging.getLogger(__name__)

_MAX_BACKOFF_S = 30.0


@lru_cache(maxsize=1)
def _semaphore() -> asyncio.Semaphore:
    return asyncio.Semaphore(get_settings().max_parallel_researchers)


def _is_throttle(exc: Exception) -> bool:
    """True when an exception looks like model/service throttling (worth retrying)."""
    if getattr(exc, "status_code", None) == 429:
        return True
    msg = str(exc).lower()
    return any(
        token in msg for token in ("429", "rate limit", "ratelimit", "throttl", "too many requests")
    )


async def _run_once(cfg, topic: str) -> ResearchResult:
    agent_id = await resolve_agent_id(cfg.researcher_agent_name)
    async with _semaphore():
        result = await run_agent(
            agent_id,
            topic,
            dispatch=RESEARCHER_DISPATCH,
            max_completion_tokens=cfg.researcher_max_completion_tokens or None,
        )
    return ResearchResult(topic=topic, summary=result.text, sources=result.sources, ok=True)


async def run_researcher(topic: str) -> ResearchResult:
    """Run one researcher agent on ``topic``; retry throttles, never raise."""
    cfg = get_settings()
    with span(f"researcher:{topic[:60]}", **{"research.topic": topic}) as sp:
        last_exc: Exception | None = None
        for attempt in range(cfg.researcher_max_retries + 1):
            try:
                return await _run_once(cfg, topic)
            except Exception as exc:  # noqa: BLE001 - classify, retry throttles, else give up
                last_exc = exc
                throttled = _is_throttle(exc)
                if throttled and attempt < cfg.researcher_max_retries:
                    delay = min(
                        cfg.researcher_retry_base_seconds * (2**attempt), _MAX_BACKOFF_S
                    ) + random.uniform(0, cfg.researcher_retry_base_seconds)
                    logger.warning(
                        "Researcher throttled for %r (attempt %d/%d); retrying in %.1fs",
                        topic,
                        attempt + 1,
                        cfg.researcher_max_retries + 1,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                break

        error = f"{type(last_exc).__name__}: {last_exc}"
        logger.warning("Researcher failed for topic %r: %s", topic, error)
        if sp is not None:
            sp.set_attribute("research.ok", False)
            sp.set_attribute("research.error", error[:500])
        return ResearchResult(
            topic=topic,
            summary=(
                "(This sub-topic could not be researched. The lead should proceed with the "
                "other findings.)"
            ),
            ok=False,
            error=error,
        )
