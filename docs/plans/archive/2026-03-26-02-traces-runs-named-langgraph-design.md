# Design: Traces Page — Root Runs Named LangGraph

## Problem

Every root trace in the LangSmith proxy shows name="LangGraph" and
slug="LangGraph". The slug filter in the proxy list is therefore useless
because filtering by any real slug matches nothing.

## Implementation Status

This defect was previously implemented. The code changes described below
are already in place. This plan exists to verify the fixes work correctly
and address any remaining issues.

## Root Cause Analysis

Three code paths contributed to the problem:

1. **finalize_root_run** (langgraph_pipeline/shared/langsmith.py):
   Reconstructed the RunTree with hardcoded name="root" instead of the
   item slug. This overwrote the correct name set at creation time when
   the trace was finalized and posted.

2. **cli.py graph invocations** (langgraph_pipeline/cli.py):
   Single-item mode, once mode, and loop mode all invoked the pipeline graph
   without run_name in the config. The LangGraph SDK fell back to
   "LangGraph" as the root run name.

3. **executor subgraph** (langgraph_pipeline/pipeline/nodes/execute_plan.py):
   The executor was invoked without any run_name config, so child runs
   from task execution also showed as "LangGraph".

## Applied Fixes

### 1. finalize_root_run — accepts item_slug parameter

Added item_slug parameter to finalize_root_run() and uses it as the
RunTree name instead of "root". Callers (archival.py) pass the slug.

### 2. cli.py — run_name added to thread_config

In all three invocation paths (single-item, once, loop), item_slug is
derived from the state and added as run_name to the config when available.

### 3. execute_plan.py — run_name config passed to executor

Passes item_slug as run_name in the executor invoke config so child
runs are named correctly.

## Key Files

| File | Change |
|------|--------|
| langgraph_pipeline/shared/langsmith.py | item_slug param on finalize_root_run |
| langgraph_pipeline/pipeline/nodes/archival.py | Passes item_slug to finalize_root_run |
| langgraph_pipeline/cli.py | run_name in thread_config in 3 paths |
| langgraph_pipeline/pipeline/nodes/execute_plan.py | run_name config on executor invoke |
| tests/langgraph/shared/test_langsmith.py | Tests finalize_root_run uses slug |

## Design Decisions

- Only add run_name when item_slug is non-empty to preserve SDK defaults
  for edge cases (single-item mode without a slug).
- No DB migration: new runs will be named correctly; old rows remain.
- No proxy changes: list_runs() already filters by name LIKE ?, which
  works once root runs carry the slug.
