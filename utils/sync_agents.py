"""Create/update the three Foundry agents from the versioned markdown prompts (idempotent).

There is no ARM/Bicep resource type for Foundry agents — they are data-plane objects — so this
script is how "infra creates the agents". Run it after provisioning and on every push to main
(the CI pipeline / azd postdeploy hook do this):

    az login
    uv run python utils/sync_agents.py            # create/update the agents, matched by name
    uv run python utils/sync_agents.py --dry-run   # offline: just print what would be synced

Agents are matched by name and updated in place, so re-running refreshes the baked instructions
(e.g. an edited prompt) without creating duplicates. The app resolves agents by NAME at runtime,
so no ids need to be injected anywhere. Git is the version source of truth.

The three agents:
- lead       (main model)  — orchestrator; no tools (returns a structured DelegationPlan).
- researcher (mini model)  — managed Grounding with Bing + think_tool / searches_remaining.
- report     (main model)  — report writer; no tools.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

from deep_research.config import get_settings
from deep_research.prompts import render
from deep_research.tools import get_today_str, searches_remaining, think_tool


@dataclass
class AgentSpec:
    name: str
    model: str
    instructions: str
    kind: str  # "lead" | "researcher" | "report"


def build_specs() -> list[AgentSpec]:
    """Assemble the three agent definitions from settings + versioned prompts."""
    cfg = get_settings()
    return [
        AgentSpec(cfg.lead_agent_name, cfg.main_model, render("lead_researcher"), "lead"),
        AgentSpec(
            cfg.researcher_agent_name,
            cfg.mini_model,
            render(
                "research_agent",
                date=get_today_str(),
                max_searches=cfg.max_searches_per_researcher,
            ),
            "researcher",
        ),
        AgentSpec(cfg.report_agent_name, cfg.main_model, render("report_writer"), "report"),
    ]


def _tools_for(kind: str):
    """Build the Foundry tool definitions for an agent (None when the agent has no tools)."""
    if kind != "researcher":
        return None
    from azure.ai.agents.models import BingGroundingTool, FunctionTool

    cfg = get_settings()
    if not cfg.bing_connection_id:
        sys.exit("BING_CONNECTION_ID is not set — populate .env from the IaC outputs.")
    bing = BingGroundingTool(connection_id=cfg.bing_connection_id)
    functions = FunctionTool(functions={think_tool, searches_remaining})
    return list(bing.definitions) + list(functions.definitions)


def _client():
    from azure.ai.agents import AgentsClient
    from azure.identity import DefaultAzureCredential

    cfg = get_settings()
    if not cfg.azure_ai_project_endpoint:
        sys.exit("AZURE_AI_PROJECT_ENDPOINT is not set — populate .env from the IaC outputs.")
    return AgentsClient(endpoint=cfg.azure_ai_project_endpoint, credential=DefaultAzureCredential())


def _dry_run(specs: list[AgentSpec]) -> None:
    print("DRY RUN — no Foundry calls. Agents that would be synced:\n")
    for spec in specs:
        tools = _tool_names(spec.kind)
        print(f"  {spec.name:28} model={spec.model:16} tools={tools}")
        print(f"      instructions: {spec.instructions[:80].strip()}…")


def _tool_names(kind: str) -> list[str]:
    if kind != "researcher":
        return []
    return ["bing_grounding", "think_tool", "searches_remaining"]


def _sync(specs: list[AgentSpec]) -> None:
    client = _client()
    with client:
        existing = {a.name: a.id for a in client.list_agents()}
        for spec in specs:
            tools = _tools_for(spec.kind)
            if spec.name in existing:
                agent = client.update_agent(
                    existing[spec.name],
                    model=spec.model,
                    name=spec.name,
                    instructions=spec.instructions,
                    tools=tools,
                )
                action = "updated"
            else:
                agent = client.create_agent(
                    model=spec.model,
                    name=spec.name,
                    instructions=spec.instructions,
                    tools=tools,
                )
                action = "created"
            print(f"  {action} {spec.name} -> {agent.id}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync the Foundry agents from the prompts.")
    parser.add_argument("--dry-run", action="store_true", help="offline; print, do not call Azure")
    args = parser.parse_args()

    specs = build_specs()
    if args.dry_run:
        _dry_run(specs)
        return 0
    _sync(specs)
    print("\nAgents synced. The app resolves them by name at runtime.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
