# Design: LangSmith Per-Item Root Trace Aggregation

**Feature:** 09-langsmith-per-item-root-trace-aggregation
**Date:** 2026-03-24
**Source:** docs/feature-backlog/09-langsmith-per-item-root-trace-aggregation.md

## Overview

Every `emit_tool_call_traces` call currently creates a new top-level `RunTree` with no
`parent_run_id`, so all tool call spans for a work item are disconnected traces in
LangSmith. This feature adds a shared root `RunTree` per work item: created in
`scan_backlog`, persisted to the item file for restart durability, threaded through
`PipelineState` → `TaskState` → `emit_tool_call_traces`, and finalized in `archive`.

## Architecture

### State schema changes

**`PipelineState`** (`langgraph_pipeline/pipeline/state.py`):

```
langsmith_root_run_id: Optional[str]
```

Populated by `scan_backlog` (fresh UUID or recovered from item file). Passed to
the executor subgraph via `execute_plan`. Cleared conceptually after `archive`
finalizes the root run (archive runs last, so no explicit reset is needed).

**`TaskState`** (`langgraph_pipeline/executor/state.py`):

```
langsmith_root_run_id: Optional[str]
```

Mapped from `PipelineState.langsmith_root_run_id` in `execute_plan` when building
`initial_task_state`. Consumed by `task_runner` when calling `emit_tool_call_traces`.

### `emit_tool_call_traces` signature change

```python
def emit_tool_call_traces(
    tool_calls: list[ToolCallRecord],
    run_name: str,
    metadata: dict[str, Any],
    parent_run_id: Optional[str] = None,
) -> None:
```

When `parent_run_id` is provided, it is passed to `RunTree(parent_run_id=parent_run_id,
...)`. No behavior change when `None` (backward-compatible).

### Root trace lifecycle

#### Creation — `scan_backlog` (`langgraph_pipeline/pipeline/nodes/scan.py`)

When an item is found (not the empty-backlog sentinel path):

1. Read the item file for an existing `## LangSmith Trace: <uuid>` metadata line.
2. If found, reconstruct the `RunTree` with `RunTree(id=existing_id, name=item_slug, ...)`.
3. If not found, create `RunTree(name=item_slug, run_type="chain", ...)`, generate UUID.
4. Write/update the `## LangSmith Trace: <uuid>` line in the item file.
5. Store the UUID in `PipelineState.langsmith_root_run_id`.

When tracing is inactive (`_tracing_active` is False), steps 1–5 are skipped and
`langsmith_root_run_id` remains `None`.

#### Threading — `execute_plan` → `TaskState`

In `execute_plan.py`, extend `initial_task_state` with:

```python
"langsmith_root_run_id": state.get("langsmith_root_run_id"),
```

#### Consumption — `task_runner.py`

Pass `langsmith_root_run_id` from `TaskState` to `emit_tool_call_traces`:

```python
emit_tool_call_traces(
    tool_calls,
    f"execute_task:{task_id}",
    {...},
    parent_run_id=state.get("langsmith_root_run_id"),
)
```

#### Finalization — `archive` (`langgraph_pipeline/pipeline/nodes/archival.py`)

Before moving the item file:

1. Read `langsmith_root_run_id` from state.
2. If set and tracing is active, reconstruct the root `RunTree` by ID, call
   `root_run.end(outputs={"item_slug": slug, "outcome": outcome})` and `root_run.post()`.
3. Strip the `## LangSmith Trace:` line from the item file content before archiving.

When tracing is inactive, steps 1–3 are skipped entirely.

## Key Files

| File | Change |
|------|--------|
| `langgraph_pipeline/pipeline/state.py` | Add `langsmith_root_run_id: Optional[str]` |
| `langgraph_pipeline/executor/state.py` | Add `langsmith_root_run_id: Optional[str]` |
| `langgraph_pipeline/shared/langsmith.py` | Add `parent_run_id` param to `emit_tool_call_traces`; add `create_root_run()` and `finalize_root_run()` helpers |
| `langgraph_pipeline/pipeline/nodes/scan.py` | Create/recover root run; write trace ID to item file; set state field |
| `langgraph_pipeline/pipeline/nodes/execute_plan.py` | Map `langsmith_root_run_id` into `initial_task_state` |
| `langgraph_pipeline/executor/nodes/task_runner.py` | Pass `parent_run_id` to `emit_tool_call_traces` |
| `langgraph_pipeline/pipeline/nodes/archival.py` | Finalize root run; strip trace ID line from item file |
| `tests/langgraph/shared/test_langsmith.py` | Tests for new helpers and updated `emit_tool_call_traces` |
| `tests/langgraph/pipeline/nodes/test_scan.py` | Tests for root trace creation in `scan_backlog` |
| `tests/langgraph/pipeline/nodes/test_archival.py` | Tests for trace finalization in `archive` |

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| New helpers `create_root_run()` / `finalize_root_run()` in `langsmith.py` | Keeps scan.py and archival.py free of RunTree imports; centralises graceful-degrade logic |
| Persist trace ID in item file | `PipelineState` is not durable across process restarts; item file survives restart |
| Read-before-write in `scan_backlog` | Idempotent: restart or resume resumes under the same root trace |
| Strip trace ID line before archiving | Completed item files in `completed-backlog` should not carry ephemeral metadata |
| `parent_run_id=None` default | Fully backward-compatible; no behavior change when tracing is off |
| Finalize in `archive`, not in `execute_plan` | `archive` is the true end-of-lifecycle node; `execute_plan` may run multiple times on retries |
