# Design: Remove redundant scan_backlog graph node

## Overview

`scan_backlog` is registered as the graph entry point but always short-circuits with `return {}` in production because the CLI pre-scans items via `_pre_scan()` before invoking the graph. This adds a no-op node to every trace. The fix removes it from the graph while keeping the function available for direct use.

## Key files to modify

- `langgraph_pipeline/pipeline/graph.py` — remove `scan_backlog` node and `NODE_SCAN_BACKLOG` constant, change entry point to `intake_analyze`, remove `has_items` conditional edge, drop `scan_backlog` import from nodes package
- `langgraph_pipeline/pipeline/edges.py` — remove `has_items` function (no longer used by the graph; CLI handles the empty-backlog check directly)
- `tests/langgraph/pipeline/test_graph_integration.py` — rewrite to match new graph topology: remove all `scan_backlog` mocks, start state with `item_path` pre-populated, drop `TestEmptyBacklog` class (that logic lives in the CLI, not the graph)

## Files left unchanged

- `langgraph_pipeline/pipeline/nodes/scan.py` — `scan_backlog` function stays; CLI imports and calls it directly via `scan_backlog_fn`
- `langgraph_pipeline/pipeline/nodes/__init__.py` — `scan_backlog` stays exported for CLI use
- `langgraph_pipeline/cli.py` — already calls `scan_backlog_fn` outside the graph; no change needed
- `tests/langgraph/pipeline/nodes/test_scan.py` — tests the standalone function; no change needed

## Graph topology after the fix

```
intake_analyze --[after_intake]--> create_plan | END
create_plan --[after_create_plan]--> execute_plan | END
execute_plan --[is_defect]--> verify_symptoms | archive
verify_symptoms --[verify_result]--> archive | create_plan
archive --> END
```

The CLI loop is responsible for calling `scan_backlog_fn()` outside the graph and only invoking the graph when an item is found. This is already the case today.

## Design decisions

- `has_items` is deleted from `edges.py` rather than kept as dead code.
- `NODE_SCAN_BACKLOG` constant is deleted from `graph.py`.
- `TestEmptyBacklog` in the integration test is deleted; the empty-backlog path is already tested in `test_scan.py` and CLI-level tests.
- Integration tests are updated to pre-populate `item_path` in the initial state, matching the real invocation pattern.
