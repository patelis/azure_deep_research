"""Live smoke test: exercise the clarifier and (optionally) a small research run.

    az login
    uv run python utils/smoke.py "Compare the battery roadmaps of Tesla, BYD and CATL"
    uv run python utils/smoke.py --full "..."   # also run the full pipeline (slow, costs money)

Needs a populated .env (AZURE_OPENAI_ENDPOINT / AZURE_AI_PROJECT_ENDPOINT / BING_CONNECTION_ID).
The agents must already be synced (utils/sync_agents.py).
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from deep_research.clarifier import clarify
from deep_research.observability import setup_observability, shutdown_observability
from deep_research.pipeline import run_research
from deep_research.runtime import aclose_runtime


async def _run(query: str, full: bool) -> None:
    setup_observability()
    print(f"# Clarifier on: {query!r}\n")
    turn = await clarify([("user", query)])
    print(f"plan_ready={turn.plan_ready}\nmessage:\n{turn.message}\n")

    if turn.plan_ready and turn.plan and full:
        print("# Running full research pipeline (this is slow)…\n")
        report = await run_research(turn.plan, progress=lambda m: print(f"  • {m}"))
        print("\n# Report\n")
        print(report.markdown)

    await aclose_runtime()
    shutdown_observability()


def main() -> int:
    parser = argparse.ArgumentParser(description="Live smoke test.")
    parser.add_argument("query", nargs="?", default="Give me an overview of solid-state batteries")
    parser.add_argument("--full", action="store_true", help="also run the full pipeline (slow)")
    args = parser.parse_args()
    asyncio.run(_run(args.query, args.full))
    return 0


if __name__ == "__main__":
    sys.exit(main())
