# Traces page: complete redesign — item-centric, usable, no raw LangSmith dump

## Summary

The Traces page is fundamentally broken and useless. Every problem
documented below was observed on the live page on 2026-03-28.

## Problems on the Traces List Page (/proxy)

### P1: Most rows are called "LangGraph" — user cannot identify items
The first 4 rows ALL say "LangGraph" as Run name AND "LangGraph" as
Item slug. The user has no way to know which work item these belong to.
The trace ID prefix is also identical ("019d329a") so they're completely
indistinguishable. The user literally cannot select a work item.

### P2: "Item slug" column is redundant
When the run name IS the slug (e.g. "03-add-dark-mode"), the slug column
just repeats it. When both are "LangGraph", both are useless. This column
adds no value.

### P3: Duration shows sub-second for full pipeline runs
Rows show 0.01s, 0.00s — these are the duplicate start/end trace events
(defect 29), not the actual pipeline run duration which took minutes.

### P4: Cost shows "—" for everything
No cost data visible in the list. The user can't see which runs were
expensive.

### P5: Model shows "—" for many entries
The first 4 "LangGraph" rows have no model. Inconsistent.

### P6: Every row has a collapsed "Details" row below it
These take vertical space even when collapsed, making the table twice
as tall. Expanding shows "Metadata JSON" — a raw developer dump that
means nothing to a user.

### P7: "RUNNING" status for items that are done
Items like "01-old-bug" and "01-bug" show RUNNING but are clearly not
running anymore. No end_time was recorded.

### P8: No grouping by work item
Traces from the same item are scattered. Multiple "LangGraph" entries
might be different phases of the same item or entirely different items.

### P9: Title says "LangSmith Traces"
Developer jargon. Should say "Execution History" or "Pipeline Runs".

## Problems on the Narrative Detail Page (/proxy/{id}/narrative)

### P10: Title still says "LangGraph" not the item slug
The header says "LangGraph COMPLETED" — which work item?

### P11: Total duration shows 0.01s for runs that took minutes
The metadata has no real timing data.

### P12: Every phase shows 0.00s duration
All 8 phases (Intake, Planning, Execution, Archival, verify_fix) show
0.00s. No actual timing information.

### P13: Duplicate phases
"Planning" appears twice (steps 02 and 03). "Execution" appears twice
(steps 04 and 05). "verify_fix" appears twice (steps 07 and 08). These
are the duplicate start/end trace events polluting the view.

### P14: "Unknown" label for verify_fix
Steps 07 and 08 say "Unknown" with "verify_fix" underneath. The mapping
from node name to human-readable phase label is incomplete.

### P15: All phases show PASS with no detail
Every phase says PASS but there's no information about what happened —
no files read, no tools called, no cost, no token count. Clicking the
▶ arrow presumably shows metadata JSON.

### P16: No link to the work item page
The user arrived here from traces — there's no way to navigate to
/item/<slug> to see the requirements, plan, or validation results.

### P17: No link to worker output logs
The planner logs, validation JSONs, and console output are all stored
but not linked from this page.

## What the User Actually Needs

The user's workflow is: "I want to understand what happened to work item
X from start to finish."

### Use Case 1: Find a work item's execution
The list should show work item SLUGS, not "LangGraph". Each row = one
work item execution. Filter by slug, date, outcome.

### Use Case 2: See the execution summary at a glance
For each item: slug, type badge, start time, REAL duration, REAL cost,
outcome (success/warn/fail), model used.

### Use Case 3: Drill down into phases
Click an item → see phases with REAL durations and costs:
- Intake: 45s, $0.08 (Haiku)
- Planning: 2m 10s, $0.52 (Opus)
- Execution: 3m 30s, $0.35 (Sonnet) — task #1.1
- Validation: 1m 15s, $0.18 (Opus) — Verdict: WARN
- Archive: 0.5s

### Use Case 4: See what the agent did in a phase
Expand a phase → see: files read, files written, bash commands run,
Claude responses (summarized, not raw JSON). This is the information
currently in the worker output logs.

### Use Case 5: Access artifacts
From any phase, link to: design doc, plan YAML, validation results,
worker output log, git commits.

### Use Case 6: Access raw data if needed
A "Show raw trace" toggle (already exists) for the technical LangSmith
data. Not the default view.

## Design Direction

Run a design competition (item 68 auto-judge) with 3 approaches.
Use the frontend-design skill. The winning design must pass ALL
acceptance criteria below.

## Acceptance Criteria

- Does the traces list show work item slugs (not "LangGraph") for
  every row? YES = pass, NO = fail
- Is the "Item slug" redundant column removed? YES = pass, NO = fail
- Does each row show the REAL duration (minutes, not 0.01s)?
  YES = pass, NO = fail
- Does each row show the REAL cost? YES = pass, NO = fail
- Are duplicate start/end trace events merged into a single row?
  YES = pass, NO = fail
- Are "RUNNING" entries that are actually finished cleaned up or
  correctly labeled? YES = pass, NO = fail
- Does clicking a row show phases with real durations and costs?
  YES = pass, NO = fail
- Are duplicate phases (Planning x2, Execution x2, verify_fix x2)
  merged? YES = pass, NO = fail
- Does "verify_fix" show as "Verification" not "Unknown"?
  YES = pass, NO = fail
- Does each phase show what the agent actually did (files, commands)?
  YES = pass, NO = fail
- Is there a link from the trace detail to /item/<slug>?
  YES = pass, NO = fail
- Is there a link to worker output logs and validation results?
  YES = pass, NO = fail
- Is raw LangSmith data hidden by default, accessible via toggle?
  YES = pass, NO = fail




## 5 Whys Analysis

**Title:** Traces page exposes infrastructure telemetry instead of work-item execution narrative

**Clarity:** 4/5 
(Excellent problem documentation with specific examples and acceptance criteria; root user need is implied rather than explicitly stated)

**5 Whys:**

1. **Why is the Traces page fundamentally broken for users?**
   Because it displays raw LangSmith infrastructure data (node names like "LangGraph", duplicate start/end events, system metadata) instead of processed information users actually need like work item slugs, real execution durations, and cost per phase.

2. **Why is raw infrastructure data being shown instead of processed user-meaningful information?**
   Because the Traces feature was built as a direct proxy into the pipeline's internal tracing system rather than as a user-facing feature that translates technical trace events into execution history aligned with work items and their lifecycle phases.

3. **Why was it designed as an infrastructure window rather than a user-facing execution narrative tool?**
   Because the team's starting point was "expose the traces the system generates" (addressing a debugging/monitoring need) rather than "help users understand what happened to their work items" (addressing a user comprehension need).

4. **Why wasn't the user need the starting point for design?**
   Because there's no clear feedback loop connecting what users actually need to comprehend with how the visibility feature is architected. The feature was built from the system perspective ("here's what we trace") rather than the user goal perspective ("here's what I need to know").

5. **Why is there a structural gap between what the system tracks internally and what users need to see?**
   Because execution visibility is currently treated as **infrastructure instrumentation exposure** (showing what the system did technically) rather than as a **user-facing work narrative** (showing the full journey of a work item from intake through validation with real costs, decisions, and actions taken by the agent).

**Root Need:** 
Users need a coherent, item-centric **execution narrative** — not raw infrastructure telemetry — that shows the complete lifecycle of a work item execution (intake → planning → execution → validation → archive) with real durations, costs per phase, agent actions, and outcomes so they can understand what happened, why, at what cost, and whether to trust the results.

**Summary:** 
The feature treats traces as internal debugging artifacts to expose rather than as a user story to tell about their work item's journey.
