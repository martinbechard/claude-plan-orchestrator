# Traces page: model filter broken and model column missing

## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


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

## LangSmith Trace: 26d83d5e-073f-45e4-bdf8-10b13209f0eb


## 5 Whys Analysis

**Title:** Model tracking gap prevents trace filtering and cost attribution

**Clarity:** 4/5 (Clear problem and suggested fix, but lacks explicit statement of user impact)

**5 Whys:**

1. Why does the model filter return no results?
   - Because the trace metadata dictionary contains only `thread_id`, `LANGSMITH_WORKSPACE_ID`, and `revision_id` — no model name is ever stored, so the `metadata_json LIKE '%<model>%'` query matches nothing.

2. Why isn't model information stored in trace metadata?
   - Because `supervisor.py` doesn't populate model data when it dispatches workers and initiates traces. The filter UI was built expecting model data that the trace-writing code never provides.

3. Why does the trace-writing code skip recording model information?
   - Because the original tracing implementation focused on execution flow (threading, workspace isolation) without considering that users would need to analyze which model performed each task.

4. Why is it essential to know which model executed each trace?
   - Because the orchestrator uses multiple models with different costs, latencies, and capabilities; without model visibility, users can't correlate costs to specific models, debug model-specific failures, or optimize which model to use for which task.

5. Why does this gap matter for this project specifically?
   - Because multi-model orchestration inherently requires observability at the model level — cost tracking, performance tuning, and debugging are model-specific concerns that become impossible without attributing every action to its model.

**Root Need:** Enable per-trace model attribution so that every execution step is traceable to the specific model that performed it, supporting cost analysis, performance optimization, and multi-model debugging.

**Summary:** The project needs end-to-end model visibility in traces to support cost tracking and optimization across its multi-model orchestration pipeline.
