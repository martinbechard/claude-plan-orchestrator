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

The fix spans three layers:

1. **Data layer (SQLite)**: Backfill root runs named "LangGraph" by resolving
   slugs from child span metadata. Backfill executor child traces that lack
   item_slug by resolving from parent run metadata.

2. **Trace emission layer**: Add item_slug to the metadata dict passed to
   emit_tool_call_traces() in task_runner.py so new executor traces carry slug
   information.

3. **Display layer (UI)**: After data fixes, the existing display_slug fallback
   chain in _enrich_run() should populate correct slugs for all rows. A Phase 0
   design competition addresses AC14 (visual distinguishability when trace ID
   prefixes are identical) and overall UI quality for the traces page.

## Key Files

### To Modify
- langgraph_pipeline/web/proxy.py -- add backfill methods
- langgraph_pipeline/web/server.py -- call backfill on startup
- langgraph_pipeline/executor/nodes/task_runner.py -- add item_slug to trace metadata
- langgraph_pipeline/shared/langsmith.py -- (verify, no changes expected)

### To Create
- tests/langgraph/web/test_proxy_backfill.py -- backfill unit tests
- tests/langgraph/shared/test_langsmith_naming.py -- forward-fix regression tests
- tests/langgraph/executor/nodes/test_task_runner_trace_metadata.py -- executor metadata tests

### Existing (Reference)
- langgraph_pipeline/web/routes/proxy.py -- _enrich_run display_slug fallback chain
- langgraph_pipeline/web/templates/proxy_list.html -- trace list template

## Design Decisions

### D1: Backfill root runs via TracingProxy SQL UPDATE

Addresses: P1
Satisfies: AC1, AC2, AC3, AC4
Approach: Add a backfill_root_run_slugs() method to TracingProxy that:
  1. Queries root runs (parent_run_id IS NULL) where name = 'LangGraph'
  2. For each, resolves the correct slug from child span metadata using the
     existing _CHILD_SLUGS_BATCH_SQL pattern
  3. Updates the root run name field and injects item_slug into metadata_json
  4. Runs in a single transaction for atomicity
  5. Returns the count of updated rows for logging
Files: langgraph_pipeline/web/proxy.py, tests/langgraph/web/test_proxy_backfill.py

### D2: Auto-backfill on web server startup

Addresses: P1
Satisfies: AC3, AC4
Approach: Call backfill_root_run_slugs() during init_proxy() so the backfill
runs automatically when the web dashboard starts. The method is idempotent --
it only targets runs where name = 'LangGraph', so re-running is safe. Log
the count of updated rows at INFO level. No manual migration step required.
Files: langgraph_pipeline/web/server.py (or proxy.py init path)

### D3: Regression tests for forward root run naming

Addresses: P2
Satisfies: AC5, AC6, AC7
Approach: Add unit tests that mock the RunTree class and verify:
  - create_root_run passes item_slug as the name parameter, not "LangGraph"
  - finalize_root_run passes item_slug as the name, falling back to "root" only
    when item_slug is empty
  - Neither function uses the SDK default name
Files: tests/langgraph/shared/test_langsmith_naming.py

### D4: Include item_slug in executor trace metadata

Addresses: P3
Satisfies: AC8, AC10
Approach: In task_runner.py, derive item_slug from plan_data.meta.source_item
(already done in _finalize_tool_calls for cost tracking) and add it to the
metadata dict passed to emit_tool_call_traces(). This ensures new executor
subgraph traces carry item_slug, enabling the child-slug resolution chain
to work for future traces.
Files: langgraph_pipeline/executor/nodes/task_runner.py, tests/langgraph/executor/nodes/test_task_runner_trace_metadata.py

### D5: Backfill executor subgraph traces with item_slug

Addresses: P3
Satisfies: AC9
Approach: Add a backfill_executor_slugs() method to TracingProxy that:
  1. Identifies child runs (parent_run_id IS NOT NULL) whose metadata_json
     lacks an item_slug field
  2. Resolves item_slug from the parent run name or metadata (since parent
     runs are now backfilled by D1)
  3. Updates the child metadata_json to include item_slug
  4. Called alongside D2 on startup, after root run backfill completes
Files: langgraph_pipeline/web/proxy.py, tests/langgraph/web/test_proxy_backfill.py

### D6: Phase 0 design competition for trace page visual distinguishability

Addresses: P4
Satisfies: AC11, AC12, AC13, AC14, AC15, AC16
Approach: After the data layer fixes (D1-D5) correct the underlying slug data,
the display_slug fallback chain in _enrich_run already populates correct slugs.
However, AC14 requires that rows be visually distinguishable even when trace ID
prefixes collide (e.g. "019d329a"). A Phase 0 design competition with
systems-designer, ux-designer, and frontend-coder explores approaches such as:
  - Showing full or longer trace ID segments
  - Color-coding or icons per unique slug
  - Row grouping visual improvements
  - Timestamp disambiguation
The design-judge selects the winner and a planner extends the YAML plan with
implementation tasks.
Files: Determined by Phase 0 winner

## Design -> AC Traceability Grid

| AC | Design Decision(s) | Approach |
|---|---|---|
| AC1 | D1 | SQL backfill updates root run name + metadata_json.item_slug |
| AC2 | D1 | Backfill resolves slug from child span metadata using existing SQL pattern |
| AC3 | D1, D2 | Backfill corrects all affected rows; auto-runs on web startup |
| AC4 | D1, D2 | Backfill targets pre-fix traces; idempotent startup execution |
| AC5 | D3 | Regression test verifies create_root_run uses item_slug as name |
| AC6 | D3 | Regression test verifies finalize_root_run sets item_slug in metadata |
| AC7 | D3 | Automated test asserts no "LangGraph" default fallback |
| AC8 | D4 | item_slug added to emit_tool_call_traces metadata dict |
| AC9 | D5 | Backfill resolves executor trace slugs from parent run |
| AC10 | D4 | item_slug in metadata enables parent work item correlation |
| AC11 | D6 | Phase 0 design explores UI improvements for item identification |
| AC12 | D1, D6 | Data backfill + possible UI enhancement |
| AC13 | D1, D6 | Data backfill + possible UI enhancement |
| AC14 | D6 | Phase 0 design addresses visual distinguishability with overlapping IDs |
| AC15 | D1, D5, D6 | Complete backfill enables historical traceability; UI presents it |
| AC16 | D1, D5, D6 | Backfill eliminates "LangGraph" from both new and historical traces |
