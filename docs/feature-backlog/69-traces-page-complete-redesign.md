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
