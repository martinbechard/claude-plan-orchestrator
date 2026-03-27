# Design: Validate fix for duplicate trace rows (start + end events)

## Status

Review Required -- the upsert fix was previously implemented and passed validation
once (1314 tests passing). This plan re-validates after subsequent codebase changes.

## Background

The LangGraph SDK emits two trace events per node: one at start (end_time=NULL) and
one at completion (end_time populated). The original code used plain INSERT, producing
two rows per run_id. The fix replaces this with an upsert pattern.

## Current State (already implemented)

1. **Unique index** on traces.run_id (proxy.py _init_db):
   CREATE UNIQUE INDEX IF NOT EXISTS idx_traces_run_id_unique ON traces (run_id)

2. **Upsert in record_run()** (proxy.py record_run):
   INSERT ... ON CONFLICT(run_id) DO UPDATE SET end_time, outputs_json, error
   Uses COALESCE to preserve existing values when the update carries NULLs.

3. **Deduplication migration** for pre-existing duplicate rows (proxy.py _init_db):
   Deletes older duplicates, keeping only the row with the highest id per run_id.

## Validation Task

Re-verify that:
- The upsert produces one row per run_id (not two)
- The dedup migration cleans pre-existing duplicates
- Trace detail queries return correct non-duplicated results
- Existing tests cover these scenarios adequately
- No regressions introduced by recent changes

## Key Files

- langgraph_pipeline/web/proxy.py -- TracingProxy.record_run() and _init_db()
- tests/langgraph/web/test_proxy.py -- test coverage for upsert behavior
