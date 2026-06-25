"""Pydantic schemas and internal data containers shared across the backend.

The ``BaseModel`` schemas are structured-output targets: ``ClarifierTurn`` for the clarifier's
``responses.parse`` call, ``DelegationPlan`` for the lead orchestrator's per-round Foundry call.
``ResearchResult`` is the internal result of one researcher run.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel, Field


class ResearchPlan(BaseModel):
    """A user-approvable research plan: an objective and the list of research tasks."""

    objective: str = Field(description="The overall research objective (a refined brief).")
    tasks: list[str] = Field(
        description="Distinct research tasks to investigate; each standalone and specific."
    )


class ClarifierTurn(BaseModel):
    """One turn of the clarifier: a clarifying question, or a proposed plan ready for review."""

    message: str = Field(
        description=(
            "The text to show the user: either a focused clarifying question, or a short "
            "presentation of the proposed research plan."
        )
    )
    plan_ready: bool = Field(
        description="True when a research plan is being presented for the user to approve/edit."
    )
    plan: ResearchPlan | None = Field(
        default=None,
        description="The proposed plan (objective + tasks); set only when plan_ready is True.",
    )
    clarification_round: int = Field(
        default=0,
        description="How many clarifying questions have been asked so far in this conversation.",
    )


class DelegationPlan(BaseModel):
    """The lead orchestrator's per-round decision: delegate more, or finish."""

    reflection: str = Field(
        description=(
            "Brief reasoning about progress so far, gaps, and why these subtasks (or why done). "
            "Use this instead of a separate think tool."
        )
    )
    subtasks: list[str] = Field(
        default_factory=list,
        description=(
            "Standalone research instructions to delegate THIS round (no acronyms, fully "
            "self-contained). Request the fewest that cover the open gaps; leave empty when done."
        ),
    )
    done: bool = Field(
        description="True when enough has been gathered and no further delegation is needed."
    )
    subagents_spawned: int = Field(
        default=0,
        description="Running count of researcher sub-agents spawned so far this run.",
    )


class TaskFinding(BaseModel):
    """One researched task's compacted finding, as carried into the report handoff."""

    task: str
    summary: str
    ok: bool = True
    error: str = ""  # the failure reason when ok is False


class LeadSynthesis(BaseModel):
    """The lead's compacted hand-off to the report writer (in-context, no external store)."""

    objective: str
    findings: list[TaskFinding] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)


@dataclass
class ResearchResult:
    """Result of one researcher sub-agent run, as seen by the lead."""

    topic: str
    summary: str
    sources: list[str] = field(default_factory=list)
    ok: bool = True  # False when the researcher could not complete (e.g. throttling)
    error: str = ""  # the failure reason when ok is False
