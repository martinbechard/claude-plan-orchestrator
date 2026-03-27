# Design: Traces Page — Root Runs Named LangGraph

## Problem

Every root trace in the LangSmith proxy shows name="LangGraph" and
slug="LangGraph". The slug filter in the proxy list is therefore useless
because filtering by any real slug matches nothing.

## Root Cause Analysis

Three code paths contribute to the problem:

1. **finalize_root_run** (`langgraph_pipeline/shared/langsmith.py:332`):
   Reconstructs the RunTree with hardcoded `name="root"` instead of the
   item slug. This overwrites the correct name set at creation time when
   the trace is finalized and posted.

2. **cli.py graph invocations** (`langgraph_pipeline/cli.py:438,505,707`):
   Single-item mode, once mode, and loop mode all invoke the pipeline graph
   without `run_name` in the config. The LangGraph SDK falls back to
   "LangGraph" as the root run name.

3. **executor subgraph** (`langgraph_pipeline/pipeline/nodes/execute_plan.py:75`):
   The executor is invoked without any `run_name` config, so child runs
   from task execution also show as "LangGraph".

Note: `worker.py:252` already sets `run_name = item_slug` correctly.

## Fix

### 1. finalize_root_run — accept item_slug parameter

Add an `item_slug` parameter to `finalize_root_run()` and use it as the
RunTree name instead of `"root"`. Update callers (archival.py) to pass
the slug.

### 2. cli.py — add run_name to thread_config

In all three invocation paths (single-item, once, loop), derive
`item_slug` from the state and add `run_name` to the config when
available.

### 3. execute_plan.py — pass run_name config to executor

Pass the item_slug as `run_name` in the executor invoke config so child
runs are named correctly.

## Key Files

| File | Change |
|------|--------|
| langgraph_pipeline/shared/langsmith.py | Add item_slug param to finalize_root_run |
| langgraph_pipeline/pipeline/nodes/archival.py | Pass item_slug to finalize_root_run |
| langgraph_pipeline/cli.py | Add run_name to thread_config in 3 paths |
| langgraph_pipeline/pipeline/nodes/execute_plan.py | Add run_name config to executor invoke |
| tests/langgraph/test_langsmith.py | Test finalize_root_run uses slug |

## Design Decisions

- Only add run_name when item_slug is non-empty to preserve SDK defaults
  for edge cases (single-item mode without a slug).
- No DB migration: new runs will be named correctly; old rows remain.
- No proxy changes: list_runs() already filters by name LIKE ?, which
  will work once root runs carry the slug.
