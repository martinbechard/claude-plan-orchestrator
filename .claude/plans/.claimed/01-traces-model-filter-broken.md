# Traces page: model filter broken and model column missing

## Status: Open

## Priority: Medium

## Summary

The model filter on the LangSmith traces page matches nothing because no model
information is stored in trace metadata. The filter UI shows model options but
querying `metadata_json LIKE ?` returns zero results. A model column should be
added to the traces table UI.

## Observed Behavior

- Selecting any model from the filter dropdown returns an empty traces list.
- The traces table has no model column.

## Root Cause

The `TracingProxy.list_runs()` filter does `metadata_json LIKE '%<model>%'` but
the LangSmith SDK stores only `thread_id`, `LANGSMITH_WORKSPACE_ID`, and
`revision_id` in root run metadata — no model name is present.

## Expected Behavior

- Each trace row should show the model(s) used.
- The model filter should match against actual model data.

## Suggested Fix

When `supervisor.py` dispatches a worker, record the model names used (e.g., from
the orchestrator config) by calling `proxy.record_run()` or a new helper that
annotates the root trace with model info. Alternatively, extract model from child
run metadata (LangGraph nodes store model info in their outputs) and backfill the
root trace `metadata_json`.

## LangSmith Trace: c3d68aab-4a5c-4e1d-aa14-2565e563033b
