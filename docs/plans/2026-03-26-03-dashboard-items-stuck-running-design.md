# Design: Dashboard Items Stuck in "Running" State

## Problem

`DashboardState.active_workers` is an in-memory dict with no dead-PID cleanup.
Two failure paths leave entries stuck permanently:

1. Worker crashes or is killed before `remove_active_worker()` is called — the PID
   is never reaped by the supervisor's `ChildProcessError` path, which pops the
   supervisor-side dict but never calls `dashboard_state.remove_active_worker()`.
2. Pipeline restart — new supervisor instance has empty `active_workers` so there
   is nothing to reap, but if the old server process was still alive the stale
   entries were in its `DashboardState`.

## Fix Overview

Two targeted changes:

### 1. Fix the `ChildProcessError` reap path in `supervisor.py`

In `_reap_finished_workers`, when `os.waitpid` raises `ChildProcessError`, the
code pops the supervisor-side record but skips the dashboard cleanup.
Fix: pop the record, compute elapsed from the stored start_time, and call
`get_dashboard_state().remove_active_worker(pid, "fail", 0.0, elapsed_s)`.

### 2. Add dead-PID sweep to `DashboardState`

Add `sweep_dead_workers()` to `DashboardState` that iterates over `active_workers`,
uses `os.kill(pid, 0)` to probe each PID, and removes entries whose processes are
gone (catching `OSError`). Call this at the top of `snapshot()` so any dashboard
read automatically clears stale entries — even entries from a previous pipeline
run that somehow survived a restart.

## Key Files

| File | Change |
|------|--------|
| `langgraph_pipeline/web/dashboard_state.py` | Add `sweep_dead_workers()` method; call it in `snapshot()` |
| `langgraph_pipeline/supervisor.py` | Fix `ChildProcessError` path to call `remove_active_worker()` |
| `tests/langgraph/test_run_pipeline.py` | Update tests if affected by new method signatures |

## Design Decisions

- `os.kill(pid, 0)` is the POSIX portable way to test PID liveness without
  sending a signal; `OSError` means the process is gone or not ours.
- Sweeping in `snapshot()` keeps the fix in one place and requires no new
  threading or background tasks.
- Duration for dead-PID entries is computed from `start_time` stored in
  `WorkerInfo` so the completion record has accurate elapsed time.
- Outcome for swept entries is `"fail"` — consistent with the crash path in
  `_reap_one_worker`.
