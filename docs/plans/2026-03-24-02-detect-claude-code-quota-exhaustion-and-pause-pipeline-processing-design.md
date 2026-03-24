# Design: Quota Exhaustion Detection — Remaining Gaps

**Work item:** docs/feature-backlog/02-detect-claude-code-quota-exhaustion-and-pause-pipeline-processing.md
**Date:** 2026-03-24

---

## Overview

Most of the quota exhaustion detection infrastructure was implemented as part of a prior
work item. This design covers the remaining gaps that were not completed:

1. A routing bug in the executor subgraph that causes an infinite loop when quota is exhausted.
2. A missing `quota_exhausted` field in the CLI initial state builder.
3. Missing unit tests for `detect_quota_exhaustion`, `probe_quota_available`, and the
   new routing paths.

---

## What is already implemented

| Component | Status |
|-----------|--------|
| `langgraph_pipeline/shared/quota.py` — `detect_quota_exhaustion()`, `probe_quota_available()` | Done |
| `executor/nodes/task_runner.py` — detects quota, resets task to pending, returns `quota_exhausted: True` | Done |
| `TaskState.quota_exhausted` field | Done |
| `PipelineState.quota_exhausted` field | Done |
| `pipeline/nodes/execute_plan.py` — propagates `quota_exhausted` to `PipelineState` | Done |
| `pipeline/edges.py` — `is_defect()` routes to END when `quota_exhausted` | Done |
| `cli.py` — `_run_quota_probe_loop()`, `_run_scan_loop()` handles quota_exhausted | Done |

---

## Gap 1: Executor routing infinite loop (critical bug)

### Problem

When `task_runner.py` detects quota exhaustion:
1. It resets the task status to `"pending"` in the plan YAML.
2. It returns `{"quota_exhausted": True}` — but does NOT increment `consecutive_failures`.

The `circuit_check` conditional edge in `executor/edges.py` only checks `consecutive_failures`.
Since failures were not incremented, it returns `ROUTE_CONTINUE` and routes to `validate_task`.

`validate_task` sees the task status as `"pending"` (not `"completed"`) and immediately
returns `{"last_validation_verdict": "PASS"}` — a no-op.

`retry_check` sees PASS and routes back to `find_next_task`, which finds the same pending
task and selects it again. The result is an infinite loop that re-fires the quota-exhausted
task until the process is killed.

### Fix

**`executor/edges.py` — `circuit_check`**: Add a guard that checks `quota_exhausted`
before checking `consecutive_failures`. If `quota_exhausted` is True, return
`ROUTE_CIRCUIT_BREAK` (which routes to END in the executor graph, causing the subgraph
to terminate so `execute_plan.py` can propagate the flag up to the pipeline).

**`executor/nodes/task_selector.py` — `find_next_task`**: Add a guard at the start of
the function that checks `quota_exhausted`. If True, set `current_task_id` to None
immediately (stops the subgraph at the `all_done` edge).

Both fixes ensure quota exhaustion terminates the executor subgraph before any further
task selection or validation occurs.

---

## Gap 2: Missing field in initial state builder

**`cli.py` — `_build_initial_state()`**: The `PipelineState` TypedDict includes
`quota_exhausted: bool`, but `_build_initial_state()` does not set it. This is a
latent defect: LangGraph checkpointing may carry a stale `True` value across invocations.

### Fix

Add `"quota_exhausted": False` to the state dict returned by `_build_initial_state()`.

---

## Gap 3: Missing unit tests

The design document for the prior work item listed `tests/langgraph/shared/test_quota.py`
as a file to create, but it was never created. Additional tests are also needed for the
newly fixed routing paths.

### Files to create/modify

| File | Tests needed |
|------|-------------|
| `tests/langgraph/shared/test_quota.py` | `detect_quota_exhaustion` (rate-limited with reset time → False; rate-limited without reset time → True; no rate limit → False); `probe_quota_available` (non-empty response → True; empty response → False) |
| `tests/langgraph/executor/test_edges.py` | `circuit_check` with `quota_exhausted=True` → `ROUTE_CIRCUIT_BREAK` even when `consecutive_failures=0` |
| `tests/langgraph/executor/nodes/test_task_selector.py` | `find_next_task` with `quota_exhausted=True` → `current_task_id: None` |
| `tests/langgraph/pipeline/test_edges.py` | `is_defect` with `quota_exhausted=True` → END |

---

## Key files to modify

| Action | File | Change |
|--------|------|--------|
| Modify | `langgraph_pipeline/executor/edges.py` | `circuit_check`: return `ROUTE_CIRCUIT_BREAK` when `quota_exhausted` is True |
| Modify | `langgraph_pipeline/executor/nodes/task_selector.py` | `find_next_task`: return `current_task_id: None` when `quota_exhausted` is True |
| Modify | `langgraph_pipeline/cli.py` | `_build_initial_state`: add `"quota_exhausted": False` |
| Create | `tests/langgraph/shared/test_quota.py` | Unit tests for quota detection and probing |
| Modify | `tests/langgraph/executor/test_edges.py` | Tests for quota_exhausted in circuit_check |
| Modify | `tests/langgraph/executor/nodes/test_task_selector.py` | Tests for quota_exhausted in find_next_task |
| Modify | `tests/langgraph/pipeline/test_edges.py` | Tests for quota_exhausted in is_defect |

---

## Design decisions

**Fix in `circuit_check` (not a new edge)**: The executor graph has a fixed topology.
Adding a new conditional edge for quota would require wiring changes across `graph.py`,
`edges.py`, and constants. Checking `quota_exhausted` inside the existing `circuit_check`
is simpler and preserves the graph structure.

**Fix in `find_next_task` as defense-in-depth**: Even with the `circuit_check` fix,
the task selector is the correct place to enforce the "stop all execution" invariant
because it is the graph's gating point for all task dispatching.

**`_build_initial_state` correction**: The LangGraph checkpointer merges state across
invocations for the same thread_id. Without an explicit `False` reset, a `quota_exhausted:
True` from a previous run would persist into the next invocation, causing the scan loop
to enter the probe loop immediately on restart even when quota has been restored.
