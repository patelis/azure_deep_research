---
name: lead_researcher_round
version: 1
description: Per-round dynamic context message passed to the lead orchestrator agent.
variables: [date, objective, tasks, findings, spawned, max_subagents, per_round, round_index, max_rounds]
updated: 2026-06-24
---
Today's date is {date}. This is delegation round {round_index} of at most {max_rounds}.

## Objective
{objective}

## Approved tasks
{tasks}

## Findings gathered so far
{findings}

## Limits for THIS round
- You have spawned {spawned} of {max_subagents} researcher sub-agents allowed for this run.
- You may request at most {per_round} subtask(s) this round. Requesting more has no effect — the
  extra are dropped.

Decide what to do. If gaps remain in the tasks above, return the fewest standalone subtasks that
close them (respecting the limit). If every task is adequately covered, set `done` true and return
no subtasks. Reply only with the structured schema.
