# Recent Completions: paginated table with full history

## Status: Open

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
