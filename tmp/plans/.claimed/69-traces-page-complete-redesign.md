# Traces page: complete redesign — item-centric, usable, no raw LangSmith dump

## Planning Instructions

This item has MANY specific problems. The plan MUST create granular tasks —
one task per problem or closely related group of problems. Do NOT create
2-3 monolithic tasks. Create 8-12 focused tasks, each independently verifiable.

## Summary

The Traces page is fundamentally broken and useless. Every problem
documented below was observed on the live page on 2026-03-28.

## Problems on the Traces List Page (/proxy)

### P1: Most rows are called "LangGraph" — user cannot identify items
The first 4 rows ALL say "LangGraph" as Run name AND "LangGraph" as
Item slug. The user has no way to know which work item these belong to.
The trace ID prefix is also identical ("019d329a") so they're completely
indistinguishable. The user literally cannot select a work item.

Root cause: the LangGraph SDK names root runs "LangGraph" by default.
create_root_run/finalize_root_run were fixed to use item_slug but many
old traces still say "LangGraph" and executor subgraph traces may too.
Fix: backfill old traces by looking up item_slug from child metadata.

### P2: "Item slug" column is redundant
When the run name IS the slug (e.g. "03-add-dark-mode"), the slug column
just repeats it. When both are "LangGraph", both are useless. Remove it.

### P3: Duration shows sub-second for full pipeline runs
Rows show 0.01s, 0.00s — these are the duplicate start/end trace events
(each node produces two rows), not the actual pipeline run duration.

### P4: Cost shows "—" for everything
No cost data visible in the list.

### P5: Model shows "—" for many entries

### P6: Every row has a collapsed "Details" row showing raw "Metadata JSON"
Takes vertical space even collapsed. Expanding shows developer dump.

### P7: "RUNNING" status for items that are done
Items show RUNNING but finished long ago — no end_time recorded.

### P8: No grouping by work item

### P9: Title says "LangSmith Traces" — developer jargon

## Problems on the Narrative Detail Page (/proxy/{id}/narrative)

### P10: Title says "LangGraph" not the item slug

### P11: Total duration shows 0.01s for runs that took minutes

### P12: Every phase shows 0.00s duration

### P13: Duplicate phases — Planning x2, Execution x2, verify_fix x2

### P14: "Unknown" label for verify_fix steps

### P15: All phases show PASS with no detail about what happened

### P16: No link to the work item page (/item/<slug>)

### P17: No link to worker output logs

## Use Cases

### UC1: Find a work item's execution
User types slug in filter → sees matching rows with real names (not LangGraph)

### UC2: See execution summary at a glance
Each row: slug, type badge, start time, REAL duration, REAL cost, outcome

### UC3: Drill down into phases
Click item → phases with REAL durations and costs per phase

### UC4: See what the agent did in a phase
Expand phase → files read/written, commands run, Claude responses summarized

### UC5: Access artifacts
Links to design doc, validation results, worker output, git commits

### UC6: Access raw data if needed
"Show raw trace" toggle for developer debugging

## Acceptance Criteria

- Does the traces list show work item slugs (not "LangGraph") for
  every row? YES = pass, NO = fail
- Is the "Item slug" redundant column removed? YES = pass, NO = fail
- Does each row show the REAL duration (minutes, not 0.01s)?
  YES = pass, NO = fail
- Does each row show the REAL cost? YES = pass, NO = fail
- Are duplicate start/end trace events merged into a single row?
  YES = pass, NO = fail
- Are stale "RUNNING" entries correctly labeled?
  YES = pass, NO = fail
- Does clicking a row show phases with real durations and costs?
  YES = pass, NO = fail
- Are duplicate phases merged? YES = pass, NO = fail
- Does "verify_fix" show as "Verification" not "Unknown"?
  YES = pass, NO = fail
- Does each phase show what the agent actually did?
  YES = pass, NO = fail
- Is there a link from trace detail to /item/<slug>?
  YES = pass, NO = fail
- Is there a link to worker output logs and validation results?
  YES = pass, NO = fail
- Is raw LangSmith data hidden by default, accessible via toggle?
  YES = pass, NO = fail

## LangSmith Trace: c5e3c8c4-fe94-4b1a-be08-c37ba7ceccef


## 5 Whys Analysis

Title: Transform traces from internal debugging tool into user-facing execution audit interface

**Clarity:** 5/5

The backlog item is exceptionally well-written with 17 specific problems, 6 concrete use cases, and 13 testable acceptance criteria. It leaves no ambiguity about what's broken or what success looks like.

**5 Whys:**

1. **Why is the current traces page useless to users?**
   → Because it displays raw LangSmith span data (all rows say "LangGraph", duplicate start/end events, metrics show 0.01s instead of real durations) instead of work item execution summaries.

2. **Why is it showing raw developer debugging output instead of a user interface?**
   → Because the page was built as a quick observability dump to verify tracing worked, not as a user-facing audit trail to answer "what happened to my item?"

3. **Why wasn't the audit interface designed when tracing was instrumented?**
   → Because tracing was added to solve an internal observability problem (did the orchestrator execute correctly?), not to solve a user problem (did my work get processed as expected?).

4. **Why is the focus on internal observability rather than user auditability?**
   → Because the orchestrator's primary requirement was execution correctness, and tracing was treated as a supporting diagnostic tool, not a first-class product interface.

5. **Why isn't auditability established as a primary product requirement?**
   → Because there's no explicit mandate that users (or the team) must be able to independently verify that specific work items were processed correctly through execution history.

**Root Need:** Establish work item execution auditability as a first-class user need and build a traces interface that surfaces execution history at the right level of abstraction (item → phases → what the agent did → outcomes → artifacts), not raw span telemetry.

**Summary:** Users need a queryable audit trail of work item executions with real metrics and clear links to artifacts, so they can verify what the orchestrator actually did—currently impossible due to treating traces as developer debugging output rather than user-facing history.
