# Design: 01 Trace Link From Completions Page Leads To Empty Execution History Page

Source item: tmp/plans/.claimed/01-in-the-completions-page-when-i-click-on-the-trace-link-in-the-trace-column-i-a.md
Requirements: docs/plans/2026-04-02-01-in-the-completions-page-when-i-click-on-the-trace-link-in-the-trace-column-i-a-requirements.md

## Architecture Overview

The trace link pipeline has four layers:

1. **Trace ID generation** -- langsmith.py create_root_run() generates a UUID
   and writes it to the item markdown file. When tracing is active, it also
   creates a LangSmith RunTree and posts it to the local proxy. When tracing
   is inactive, only the UUID is generated (no RunTree).

2. **Trace data persistence** -- When tracing is active, the LangSmith SDK
   posts RunTree data (root + child spans) to the local proxy, which stores
   them in the SQLite traces table. When tracing is inactive, no trace data
   is posted.

3. **Completion recording** -- supervisor.py reads the trace UUID from the
   item file and passes it to proxy.record_completion(). If no matching
   trace row exists, _ensure_synthetic_trace_row() inserts a bare root row
   with no children and "synthetic": true in metadata.

4. **Frontend rendering** -- completions.html links to
   /execution-history/{run_id}. That page fetches /api/execution-tree/{run_id}
   and renders the tree. When the tree is empty (synthetic trace), it shows
   a generic "No detailed trace data available" message.

### Root Cause

All completion run_ids point to synthetic trace roots with zero children.
The execution history page works correctly but has no tree data to show.
Meanwhile, real trace trees (105K+ child rows, 10K+ root runs) exist in
the traces table but are disconnected from the completion run_ids.

The disconnect occurs because:
- When tracing is inactive, create_root_run() generates a UUID but no
  RunTree is posted, so no real trace data lands in the DB for that UUID.
- _ensure_synthetic_trace_row() creates a bare root trace so the page
  doesn't 404, but the trace has no children.

The fix must bridge completions to their real trace trees. Real root
traces often share the same slug/name as the completion (set in
create_root_run() via item_slug). A secondary fallback shows meaningful
completion metadata when no real trace tree can be found.

## Key Files to Modify

| File | Action |
|------|--------|
| langgraph_pipeline/web/proxy.py | Add find_real_trace_for_completion() and migrate_completion_run_ids() |
| langgraph_pipeline/web/routes/execution_history.py | Modify to redirect to real trace when synthetic detected |
| langgraph_pipeline/web/static/execution-history.js | Modify renderEmptyTree() to show completion summary data |
| langgraph_pipeline/web/templates/execution_history.html | Pass completion context data for fallback display |
| tests/langgraph/web/test_proxy.py | Add tests for find_real_trace_for_completion() |
| tests/langgraph/web/test_execution_history.py | Add tests for synthetic-to-real redirect |

## Design Decisions

### D1: Resolve real trace root by slug matching

- **Addresses:** P1
- **Satisfies:** AC2, AC3, AC4
- **Approach:** Add find_real_trace_for_completion() to proxy.py. When the
  execution history page detects a synthetic trace (metadata_json contains
  "synthetic": true), it looks up the completion's slug from the completions
  table, then queries traces for a non-synthetic root run (parent_run_id IS
  NULL) matching that slug name. If a real trace root is found, the route
  redirects (HTTP 302) to /execution-history/{real_run_id}. This transparently
  resolves the empty page for completions that have matching real traces.

  Query: SELECT run_id FROM traces WHERE parent_run_id IS NULL
         AND name = ? AND run_id != ?
         AND (metadata_json IS NULL OR metadata_json NOT LIKE '%"synthetic"%')
         ORDER BY start_time DESC LIMIT 1

  The NOT LIKE check avoids matching other synthetic traces. ORDER BY
  start_time DESC picks the most recent matching trace (in case a work item
  was retried).

- **Files:** langgraph_pipeline/web/proxy.py, langgraph_pipeline/web/routes/execution_history.py

### D2: Startup migration to re-link completion run_ids

- **Addresses:** P1
- **Satisfies:** AC2, AC4, AC5
- **Approach:** Add migrate_completion_run_ids() called from _init_db().
  For each completion whose run_id points to a synthetic trace row, find a
  real root trace by slug (same query as D1). If found, update the
  completion's run_id to the real trace run_id. This permanently fixes the
  data so future navigations work without the D1 redirect. The migration
  is idempotent and runs at each startup (no-op once all completions are
  re-linked).

  Also update the completion's attempts_history JSON to reflect the new
  run_id for the most recent attempt.

- **Files:** langgraph_pipeline/web/proxy.py

### D3: Show completion summary when no real trace exists

- **Addresses:** P1
- **Satisfies:** AC2, AC4
- **Approach:** When the tree is empty and no real trace can be found (D1
  found no match), show a meaningful completion summary instead of the generic
  "No detailed trace data available" message. The execution history route
  passes completion data (outcome, cost, duration, finished_at, attempt
  history) to the template via data attributes. The JS renderEmptyTree()
  renders this data as a structured summary card with outcome badge, cost,
  duration, and timestamp. This ensures the page is never perceived as
  "empty" even when no trace tree exists.
- **Files:** langgraph_pipeline/web/routes/execution_history.py, langgraph_pipeline/web/templates/execution_history.html, langgraph_pipeline/web/static/execution-history.js

### D4: Execution history API tree endpoint handles synthetic redirect

- **Addresses:** P1
- **Satisfies:** AC2, AC3
- **Approach:** The /api/execution-tree/{run_id} endpoint checks if the
  returned tree is empty and the root trace is synthetic. If so, it applies
  the same slug-matching logic from D1 to find a real trace root and returns
  that tree instead. This means the page-level redirect (D1) and the API
  endpoint both handle the synthetic case, providing defense in depth.
  The API response includes a "resolved_run_id" field when the run_id was
  resolved from a synthetic to a real trace, so the client JS can update
  the URL if needed.
- **Files:** langgraph_pipeline/web/routes/execution_history.py, langgraph_pipeline/web/proxy.py

## Design -> AC Traceability Grid

| AC | Design Decision(s) | Approach |
|----|-------------------|----------|
| AC1 | (already works) | Navigation to Execution History page via Trace link already functions correctly |
| AC2 | D1, D2, D3, D4 | Resolve real trace by slug (D1/D2/D4); show completion summary when no real trace (D3) |
| AC3 | D1, D4 | Redirect to real trace run_id ensures the identifier is correctly resolved end-to-end |
| AC4 | D1, D2, D3 | Migration (D2) re-links all completions; redirect (D1) catches any remaining; fallback (D3) handles rest |
| AC5 | D2 | Migration specifically handles the b9036e15 trace ID by re-linking its completion to a real trace |
