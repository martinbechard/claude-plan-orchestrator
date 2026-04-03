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
traces share the same slug/name as the completion (set in create_root_run()
via item_slug). A secondary fallback shows meaningful completion metadata
when no real trace tree can be found.

## Key Files to Modify

| File | Action |
|------|--------|
| langgraph_pipeline/web/proxy.py | Add find_real_trace_for_completion(), is_synthetic_trace(), migrate_completion_run_ids() |
| langgraph_pipeline/web/routes/execution_history.py | Redirect synthetic traces to real traces; pass completion context for fallback |
| langgraph_pipeline/web/static/execution-history.js | Update renderEmptyTree() to show completion summary card |
| langgraph_pipeline/web/templates/execution_history.html | Add data attributes for completion context |
| tests/langgraph/web/test_proxy.py | Add tests for new proxy methods |
| tests/langgraph/web/test_execution_history.py | Add tests for synthetic-to-real redirect |

## Design Decisions

### D1: Resolve real trace root by slug matching

- **Addresses:** P1, UC1
- **Satisfies:** AC2, AC3, AC4, AC5
- **Approach:** Add find_real_trace_for_completion(run_id) to proxy.py.
  Given a synthetic trace run_id, look up the completion's slug from the
  completions table, then query traces for a non-synthetic root run
  (parent_run_id IS NULL) matching that slug name. Return the real run_id
  or None.

  Query: SELECT run_id FROM traces WHERE parent_run_id IS NULL
         AND name = ? AND run_id != ?
         AND (metadata_json IS NULL OR metadata_json NOT LIKE '%"synthetic"%')
         ORDER BY start_time DESC LIMIT 1

  Also add is_synthetic_trace(run_id) helper that checks metadata_json for
  the "synthetic" flag.

- **Files:** langgraph_pipeline/web/proxy.py

### D2: Startup migration to re-link completion run_ids

- **Addresses:** P1
- **Satisfies:** AC2, AC4, AC5
- **Approach:** Add migrate_completion_run_ids() called from _init_db().
  For each completion whose run_id points to a synthetic trace row, find a
  real root trace by slug (same query as D1). If found, update the
  completion's run_id to the real trace run_id. This permanently fixes the
  data so future navigations work without runtime redirect. The migration
  is idempotent and runs at each startup (no-op once all completions are
  re-linked). Also update the completion's attempts_history JSON to reflect
  the new run_id for the most recent attempt.

- **Files:** langgraph_pipeline/web/proxy.py

### D3: Show completion summary when no real trace exists

- **Addresses:** P1, UC1
- **Satisfies:** AC2, AC6
- **Approach:** When the tree is empty and no real trace can be found (D1
  found no match), show a meaningful completion summary instead of the
  generic "No detailed trace data available" message. The execution history
  route passes completion data (outcome, cost, duration, finished_at) to
  the template via data attributes. The JS renderEmptyTree() renders this
  as a structured summary card with outcome badge, cost, duration, and
  timestamp. This ensures the page is never perceived as "empty."
- **Files:** langgraph_pipeline/web/routes/execution_history.py, langgraph_pipeline/web/templates/execution_history.html, langgraph_pipeline/web/static/execution-history.js

### D4: Execution history route and API handle synthetic redirect

- **Addresses:** P1, UC1
- **Satisfies:** AC1, AC2, AC3, AC5
- **Approach:** In execution_history.py: (1) execution_history_page() checks
  if the trace is synthetic via is_synthetic_trace(). If so, calls
  find_real_trace_for_completion(run_id). If a real run_id is found, returns
  RedirectResponse(302) to /execution-history/{real_run_id}. (2) The
  /api/execution-tree/{run_id} endpoint applies the same resolution when
  the tree is empty and the trace is synthetic, returning the real tree
  with a "resolved_run_id" field. (3) The route passes completion data
  (outcome, cost, duration, finished_at) to the template context for the
  D3 fallback display.
- **Files:** langgraph_pipeline/web/routes/execution_history.py, langgraph_pipeline/web/proxy.py

## Design -> AC Traceability Grid

| AC | Design Decision(s) | Approach |
|----|-------------------|----------|
| AC1 | D4 | Navigation already works; redirect (D4) ensures correct trace loads after navigation |
| AC2 | D1, D2, D3, D4 | Resolve real trace by slug (D1/D2/D4); show completion summary when no real trace (D3) |
| AC3 | D1, D4 | Multiple items work because slug-matching resolves each completion to its specific real trace |
| AC4 | D1, D2 | find_real_trace_for_completion() resolves the correct identifier; migration (D2) fixes at startup |
| AC5 | D1, D2, D4 | Trace identifier resolved via slug match; migration re-links permanently; API endpoint resolves on fetch |
| AC6 | D1, D3 | Slug-based resolution (D1) ensures displayed trace matches clicked item; fallback (D3) shows correct completion metadata |


## Acceptance Criteria

AC1: Does clicking a Trace link in the Completions page navigate the user to the Execution History page? YES = pass, NO = fail
  Origin: Derived from C1 [FACT] (made verifiable)
  Belongs to: P1
  Source clauses: [C1]

AC2: Is the Execution History page non-empty (i.e., trace data is visibly rendered) after navigating via a Trace link? YES = pass, NO = fail
  Origin: Derived from C2 [PROB] (inverse — "page is empty" → "page is non-empty")
  Belongs to: P1
  Source clauses: [C2]

AC3: Does the non-empty behavior hold for multiple different items, not just a single trace? YES = pass, NO = fail
  Origin: Derived from C2 [PROB] (inverse — "no matter what item" is empty → every item shows data)
  Belongs to: P1
  Source clauses: [C2]

AC4: Does the Trace link in the Completions page correctly encode and transmit the trace identifier in the URL or navigation parameters to the Execution History page? YES = pass, NO = fail
  Origin: Derived from C3 [GOAL] (operationalized — "correctly transmit the trace identifier" → verifiable encoding check)
  Belongs to: UC1
  Source clauses: [C3]

AC5: Does the Execution History page receive the trace identifier and use it to fetch and load the corresponding trace data? YES = pass, NO = fail
  Origin: Derived from C3 [GOAL] (operationalized — "trace data is loaded" → verifiable data-fetch check)
  Belongs to: UC1
  Source clauses: [C3]

AC6: Does the displayed trace data on the Execution History page correspond to the specific item whose Trace link was clicked? YES = pass, NO = fail
  Origin: Derived from C3 [GOAL] (operationalized — "displayed instead of showing empty content" → correct-content verification)
  Belongs to: UC1
  Source clauses: [C1, C3]
