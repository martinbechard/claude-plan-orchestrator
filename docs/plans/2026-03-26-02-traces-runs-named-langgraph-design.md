# Design: Traces Page — Root Runs Named LangGraph

## Problem

Every root trace in the LangSmith proxy shows `name="LangGraph"` and
`slug="LangGraph"`. The slug filter in the proxy list is therefore useless
because filtering by any real slug matches nothing.

## Root Cause

`worker.py` invokes the pipeline graph without a `run_name` config key:

```python
thread_config = {"configurable": {"thread_id": thread_id}}
graph.invoke(initial_state, config=thread_config)
```

The LangGraph SDK falls back to "LangGraph" as the root run name when no
`run_name` is present in the config. The `item_slug` only appears in child
run metadata, never in the root run's `name` column.

`list_runs()` in `proxy.py` filters by `name LIKE ?`, so slug-based filtering
is broken for existing and new runs.

## Fix

### `langgraph_pipeline/worker.py`

Add `"run_name": item_slug` at the top level of the LangGraph invocation
config when `item_slug` is non-empty. The LangSmith SDK reads `run_name` from
the config and uses it as the `name` field on the root run.

```python
thread_config = {"configurable": {"thread_id": thread_id}}
if item_slug:
    thread_config["run_name"] = item_slug
```

This is a one-line addition to `_build_initial_state` or inline in `main()`.

### Test coverage

Add `tests/langgraph/test_worker.py` with unit tests verifying:
- `_build_initial_state()` returns the expected PipelineState
- The `thread_config` built in `main()` includes `run_name=item_slug` when slug is non-empty
- When `item_slug` is empty, `run_name` is absent from the config (no empty-string name)

## Key Files

| File | Change |
|------|--------|
| `langgraph_pipeline/worker.py` | Add `run_name` to LangGraph invoke config |
| `tests/langgraph/test_worker.py` | New unit tests for worker config construction |

## Design Decisions

- Only add `run_name` when `item_slug` is non-empty to preserve the SDK
  default for edge cases (e.g. single-item mode invoked without a slug).
- No DB migration needed: new runs will be named correctly; old "LangGraph"
  rows are already in the DB and remain as-is.
- No proxy changes required: `list_runs()` already filters by `name LIKE ?`,
  which will work correctly once root runs carry the slug as their name.
