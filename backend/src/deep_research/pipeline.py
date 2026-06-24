"""End-to-end research pipeline: approved plan -> lead delegation -> compaction -> report.

This is the in-process entry point the py-shiny frontend calls inside an ``ExtendedTask``. It wires
the phases and reports human-readable progress via an optional callback. Observability is set up
lazily (idempotent) so a single import-and-call works from the UI.
"""

from __future__ import annotations

import logging

from deep_research.lead import Progress, run_lead
from deep_research.observability import setup_observability, span
from deep_research.report import ReportResult, write_report
from deep_research.schemas import ResearchPlan

logger = logging.getLogger(__name__)


async def run_research(plan: ResearchPlan, progress: Progress | None = None) -> ReportResult:
    """Run the full research pipeline for an approved ``plan`` and return the final report."""
    setup_observability()
    with span("deep_research", **{"research.objective": plan.objective[:120]}):
        if progress:
            progress("Starting research…")
        synthesis = await run_lead(plan, progress)
        if progress:
            progress("Writing the final report…")
        report = await write_report(synthesis)
        if progress:
            progress("Report ready.")
        return report
