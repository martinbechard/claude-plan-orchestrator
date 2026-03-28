# Design: Test Traceability Validation

Source work item: tmp/plans/.claimed/test-traceability-validation.md
Requirements: docs/plans/2026-03-28-test-traceability-validation-requirements.md
Date: 2026-03-28

## Problem Summary

The traces page shows "LangGraph" as the run name and item slug for most rows
because the LangGraph SDK defaults root run names to "LangGraph". A forward fix
was deployed in create_root_run/finalize_root_run but historical traces were
never backfilled. Executor subgraph traces also lack item_slug in their
metadata, breaking the child-slug resolution fallback chain.

## Architecture Overview

The fix spans two layers:

1. **Data layer (backfill)**: Backfill root runs named "LangGraph" by resolving
   slugs from child span metadata. Backfill executor child traces that lack
   item_slug by resolving from parent run metadata.

2. **Trace emission layer (forward fix)**: Add item_slug to the metadata dict
   passed to emit_tool_call_traces() in task_runner.py so new executor traces
   carry slug information.

No UI template changes are needed. Although P1, P2, and UC1 are tagged UI, the
root cause is data-layer: the existing display_slug fallback chain in
_enrich_run() (routes/proxy.py:224-230) already populates correct slugs when
data is correct. Once backfill corrects historical data, the slug column will
differ across traces even when trace ID prefixes collide, satisfying P2's
visual distinguishability requirement (AC4, AC5) without template changes.

## Key Files

### To Modify
- langgraph_pipeline/web/proxy.py -- add backfill methods to TracingProxy
- langgraph_pipeline/web/server.py -- call backfill on startup via init_proxy
- langgraph_pipeline/executor/nodes/task_runner.py -- add item_slug to executor trace metadata

### To Create
- tests/langgraph/web/test_proxy_backfill.py -- backfill unit tests
- tests/langgraph/executor/nodes/test_task_runner_trace_metadata.py -- executor metadata tests

### Existing (Reference)
- langgraph_pipeline/web/routes/proxy.py -- _enrich_run display_slug fallback chain
- langgraph_pipeline/web/templates/proxy_list.html -- trace list template (no changes needed)
- langgraph_pipeline/web/proxy.py -- _CHILD_SLUGS_BATCH_SQL_TEMPLATE (reused by backfill)

## Design Decisions

### D1: Backfill root runs via TracingProxy SQL UPDATE

Addresses: P1, FR1
Satisfies: AC1, AC2, AC3, AC10, AC11, AC13
Approach: Add a backfill_root_run_slugs() method to TracingProxy that:
  1. Queries root runs (parent_run_id IS NULL) where name = 'LangGraph'
  2. For each, resolves the correct slug from child span metadata using the
     existing _CHILD_SLUGS_BATCH_SQL pattern
  3. Updates the root run name field and injects item_slug into metadata_json
  4. Runs in a single transaction for atomicity
  5. Returns the count of updated rows for logging
  6. Post-fix traces already have correct names, so the WHERE name='LangGraph'
     clause ensures they are unaffected (AC13)
Files: langgraph_pipeline/web/proxy.py, tests/langgraph/web/test_proxy_backfill.py

### D2: Auto-backfill on web server startup

Addresses: P1, FR1
Satisfies: AC3, AC10
Approach: Call backfill_root_run_slugs() and backfill_executor_slugs() during
init_proxy() so the backfill runs automatically when the web dashboard starts.
Both methods are idempotent -- they only target runs that still need correction.
Log the count of updated rows at INFO level. No manual migration step required.
Files: langgraph_pipeline/web/server.py (or proxy.py init path)

### D3: Include item_slug in executor trace metadata

Addresses: P3
Satisfies: AC6, AC7
Approach: In task_runner.py, derive item_slug from plan_data.meta.source_item
(already done in _finalize_tool_calls for cost tracking) and add it to the
metadata dict passed to emit_tool_call_traces(). This ensures new executor
subgraph traces carry item_slug, enabling the child-slug resolution chain
to work for future traces and satisfying the executor-level identifiability
requirement.
Files: langgraph_pipeline/executor/nodes/task_runner.py, tests/langgraph/executor/nodes/test_task_runner_trace_metadata.py

### D4: Backfill executor subgraph traces with item_slug

Addresses: P3, FR1
Satisfies: AC6, AC7, AC12
Approach: Add a backfill_executor_slugs() method to TracingProxy that:
  1. Identifies child runs (parent_run_id IS NOT NULL) whose metadata_json
     lacks an item_slug field
  2. Resolves item_slug from the parent run name or metadata (since parent
     runs are now backfilled by D1)
  3. Updates the child metadata_json to include item_slug
  4. Called alongside D2 on startup, after root run backfill completes
Files: langgraph_pipeline/web/proxy.py, tests/langgraph/web/test_proxy_backfill.py

### D5: UI distinguishability via corrected data (no template changes)

Addresses: P2, UC1
Satisfies: AC4, AC5, AC8, AC9
Approach: No UI template changes needed. The existing display_slug fallback
chain in _enrich_run() works as follows:
  1. Check metadata_json for slug or item_slug
  2. Use run name if it is not "LangGraph"
  3. Fall back to child-aggregated slug
After D1 and D4 correct the underlying data, every trace row will have a
correct, distinct item slug. The slug column will differ across unrelated
traces even when trace ID prefixes collide ("019d329a"), satisfying AC4
and AC5. UC1 is satisfied because display_slug shows the correct item slug
without requiring drill-down (AC8) and shows a human-readable slug rather
than a framework default (AC9).
Files: No changes (verified by existing _enrich_run logic)

## Design -> AC Traceability Grid

| AC | Design Decision(s) | Approach |
|---|---|---|
| AC1 | D1 | SQL backfill updates root run name + metadata_json.item_slug |
| AC2 | D1 | Backfill resolves slug from child span metadata using existing SQL pattern |
| AC3 | D1, D2 | Backfill corrects all affected rows; auto-runs on web startup |
| AC4 | D5 | Once data is correct, slug column differs across unrelated traces |
| AC5 | D5 | item_slug column provides non-ID distinguisher after backfill |
| AC6 | D3, D4 | Forward fix + backfill ensure executor traces carry item_slug |
| AC7 | D3, D4 | Executor traces identifiable via item_slug in metadata |
| AC8 | D5 | Correct display_slug shown in list view without drill-down |
| AC9 | D5 | Human-readable slug replaces "LangGraph" framework default |
| AC10 | D1, D2 | Backfill updates previously "LangGraph"-named root traces |
| AC11 | D1 | Backfill resolves item_slug from child span metadata |
| AC12 | D4 | Executor subgraph traces updated from parent run data |
| AC13 | D1 | WHERE name='LangGraph' clause skips post-fix traces |
