# Recent Completions: paginated table with full history

## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


## Status: Open

## RETURNED FROM COMPLETED — No Visible Implementation

This item was previously marked as completed but there is no /completions page
and no "View all" link in the dashboard Recent Completions panel. Needs
re-verification and completion.

## Priority: Medium

## Summary

The Recent Completions panel on the dashboard only shows the last 4-20
completions held in memory/DB. There is no way to page back through older
completions. A dedicated paginated view is needed so users can review the full
completion history across sessions.

## Expected Behavior

- The dashboard Recent Completions panel keeps its live SSE-driven view for
  the most recent items (last ~10), acting as a live feed.
- A "View all" link at the bottom of the panel navigates to /completions —
  a dedicated paginated completions history page.
- /completions shows a full table of all rows in the completions DB table,
  paginated (e.g. 50 per page), sorted by finished_at descending.
- Filter controls: slug substring, outcome (success/warn/fail), date range.
- Each slug in the table links to /item/<slug> (feature 06).
- The page uses standard pagination controls consistent with the Traces page.

## Implementation Notes

- Backend: new GET /completions endpoint in routes/completions.py.
- Add count_completions() and list_completions(page, page_size, slug,
  outcome, date_from, date_to) methods to TracingProxy (list_completions
  already exists with a limit param; extend it with offset and filters).
- The COMPLETIONS_LIMIT constant in proxy.py (currently 20) controls the
  dashboard SSE feed only; the /completions page queries without that cap.
- Summary stats at top of page: total completions, success/warn/fail counts,
  total cost across all completions.




## 5 Whys Analysis

Title: Paginated completion history view needed for system observability

Clarity: 4

5 Whys:

1. **Why is a paginated completions page needed?**
   Because the dashboard Recent Completions panel shows only the last 4-20 completions in memory, and there's no way to view older completions or the full history beyond what's currently cached.

2. **Why do users need to access the full completion history, not just recent items?**
   Because understanding what work was actually completed across sessions—including what failed, was retried, or succeeded—is essential for verifying that specific items were processed and tracking the system's work output over time.

3. **Why must users manually inspect the full completion history themselves?**
   Because the orchestrator autonomously processes task items (features, defects) through a multi-step pipeline, and diagnosing why items are failing, retrying, or being abandoned requires examining the complete execution record rather than live summaries.

4. **Why is direct access to the execution record critical rather than relying on dashboards or reports?**
   Because debugging a complex autonomous system requires discovering patterns—correlations between item type, timestamps, outcomes, and error conditions—that only become apparent when examining the full temporal dataset in context.

5. **Why must the operator have this low-level diagnostic capability built into the system?**
   Because the orchestrator's effectiveness depends on continuous iteration: the operator must be able to observe failures, identify patterns, formulate hypotheses about root causes, and validate fixes without requiring external tools or log-diving—visibility drives iteration.

Root Need: The autonomous orchestrator's operator requires complete, queryable historical visibility into task completion outcomes across all sessions to diagnose system failures, iterate on improvements, and validate that the pipeline is functioning as intended.

Summary: Users cannot diagnose why the autonomous task orchestrator is failing without access to full completion history with filtering and temporal context.
