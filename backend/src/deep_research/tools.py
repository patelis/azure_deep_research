"""Function tools dispatched to the researcher agent.

These are plain ``async`` functions; their JSON-schema definitions are baked into the researcher
Foundry agent by ``utils/sync_agents.py`` and dispatched by the runtime. Grounding with Bing is a
*managed* tool baked into the agent definition (not here) — it is server-side, so its searches
cannot be counted in code. ``searches_remaining`` is therefore **advisory**: it restates the soft
budget the prompt already gives the agent. The real spend guards are the hard subagent ceiling and
per-researcher token cap (see ``lead.py`` / ``config.py``).
"""

from __future__ import annotations

from datetime import datetime

from deep_research.config import get_settings


def get_today_str() -> str:
    """Return the current date in a human-readable format."""
    return datetime.now().strftime("%a %b %d, %Y")


async def think_tool(reflection: str) -> str:
    """Record a strategic reflection on research progress to plan next steps.

    Use after each search to assess findings, identify gaps, and decide whether to keep
    searching or conclude.

    Args:
        reflection: Your reflection on findings so far, gaps, and next steps.
    """
    return f"Reflection recorded: {reflection}"


async def searches_remaining() -> str:
    """Report the soft web-search budget for this research task before searching again.

    Call this to plan your queries so you stay within budget, then summarize and conclude.
    """
    cap = get_settings().max_searches_per_researcher
    if not cap:
        return "Your web-search budget for this task is unlimited; still, be economical."
    return (
        f"Your soft budget for this task is {cap} web searches. Spend them on the highest-value "
        "queries, then stop searching and write up what you found."
    )


# Local implementations the researcher agent's tool calls dispatch to.
RESEARCHER_DISPATCH = {
    "think_tool": think_tool,
    "searches_remaining": searches_remaining,
}
