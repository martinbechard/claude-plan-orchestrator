# Work item page: show last run trace and average velocity

## Summary

Two missing pieces of information on the /item/<slug> detail page:

1. The last run (trace) associated with the item should be prominently
   linked so the user can quickly drill into the most recent execution.
   Currently traces are listed at the bottom but the most recent one
   should be surfaced near the status.

2. The average velocity (tokens per minute) during execution should be
   displayed as a badge/tag next to the pipeline stage status. This
   value should come from the completions table or the active worker's
   current velocity. This same value drives the colour of the dashboard
   timeline bars in velocity mode.

## Acceptance Criteria

- Does the item detail page show a link to the most recent trace near
  the top (not just in the traces table at the bottom)?
  YES = pass, NO = fail
- Does the item detail page show average tokens/min as a tag next to
  the pipeline stage badge? YES = pass, NO = fail
- Is the velocity value consistent with what the dashboard timeline
  shows for the same item? YES = pass, NO = fail

## LangSmith Trace: 12c69a35-a852-43c7-8650-9ba3fb619ac4


## 5 Whys Analysis

Title: Surface execution performance metrics alongside item status for quick assessment

Clarity: 4/5

5 Whys:
1. Why should the last trace and velocity be shown at the top of the item page?
   → Users reviewing item status need immediate context about execution performance to understand what that status actually means for the item's health.

2. Why do users need execution performance visible when reviewing status?
   → Because status alone (running, completed, failed) is incomplete—users need to know if execution is fast or slow, expensive, stable, or error-prone to make decisions.

3. Why does execution performance matter more than the raw status?
   → Because two items with the same "running" status are fundamentally different if one has high velocity and one is stalled, affecting prioritization and debugging urgency.

4. Why can't users find this information on the current page?
   → Because execution metrics (velocity from completions table) and traces are either not calculated at all or buried in tables at the bottom, requiring scrolling and extra cognitive load.

5. Why are execution metrics treated as secondary data instead of primary context?
   → Because the page was originally designed to emphasize state/stage information first, treating detailed execution characteristics as supplementary details for users who needed to dig deeper.

Root Need: The item detail page should display execution performance metrics (velocity, last trace) alongside status information so users can quickly assess whether an item is healthy, fast, or problematic without scrolling or context-switching.

Summary: Users need execution performance visibility at the top of item pages to make rapid optimization and debugging decisions, not buried in tables.
