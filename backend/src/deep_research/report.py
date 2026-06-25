"""Report writer: a Foundry agent that turns the lead's synthesis into a cited markdown report.

The report agent is given the objective, the per-task findings, and the aggregated source URLs,
and writes a comprehensive markdown report. We **guarantee** a ``### Sources`` section listing
every used citation (appending any the model omitted), and append a transparent completeness note
if any sub-topic could not be researched.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from deep_research.config import get_settings
from deep_research.observability import span
from deep_research.prompts import render
from deep_research.runtime import resolve_agent_id, run_agent
from deep_research.schemas import LeadSynthesis
from deep_research.tools import get_today_str


@dataclass
class ReportResult:
    """The final report and the sources backing it."""

    markdown: str
    sources: list[str] = field(default_factory=list)


def _format_synthesis(synthesis: LeadSynthesis) -> str:
    """Render the lead's synthesis as the report writer's brief."""
    parts = [f"Research objective:\n{synthesis.objective}", "", "Findings by task:"]
    for i, f in enumerate(synthesis.findings, 1):
        status = "" if f.ok else " (incomplete)"
        parts.append(f"\n## Task {i}: {f.task}{status}\n{f.summary}")
    if synthesis.sources:
        parts.append("\n\nSources collected (cite these):")
        parts += [f"- {u}" for u in synthesis.sources]
    return "\n".join(parts)


def _ensure_sources_section(markdown: str, sources: list[str]) -> str:
    """Guarantee a '### Sources' section listing every used citation."""
    if not sources:
        return markdown
    has_header = "### sources" in markdown.lower()
    missing = [u for u in sources if u not in markdown]
    if has_header and not missing:
        return markdown
    if not has_header:
        body = "\n".join(f"{i}. {u}" for i, u in enumerate(sources, 1))
        return f"{markdown.rstrip()}\n\n### Sources\n{body}\n"
    # Header exists but some sources are unlisted — append the missing ones.
    extra = "\n".join(f"- {u}" for u in missing)
    return f"{markdown.rstrip()}\n{extra}\n"


async def write_report(synthesis: LeadSynthesis) -> ReportResult:
    """Run the report Foundry agent and return the cited markdown report."""
    cfg = get_settings()
    report_id = await resolve_agent_id(cfg.report_agent_name)
    brief = render("final_report", date=get_today_str(), synthesis=_format_synthesis(synthesis))

    with span("report", **{"report.findings": len(synthesis.findings)}):
        result = await run_agent(report_id, brief)

    sources: list[str] = list(synthesis.sources)
    for url in result.sources:
        if url not in sources:
            sources.append(url)

    markdown = _ensure_sources_section(result.text, sources)

    incomplete = [f for f in synthesis.findings if not f.ok]
    if incomplete:
        lines = ["\n\n> _Completeness note: the following sub-topics could not be fully researched"]
        lines.append("> (the report reflects what was gathered):_")
        for f in incomplete:
            reason = (f.error or "unknown error").splitlines()[0][:200]
            lines.append(f">   - {f.task} — {reason}")
        markdown += "\n".join(lines) + "\n"

    return ReportResult(markdown=markdown, sources=sources)
