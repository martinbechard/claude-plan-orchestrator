# Design: Dashboard Items Stuck in "Running" State

## Problem

`DashboardState.active_workers` is an in-memory dict with no dead-PID cleanup.
Two failure paths leave entries stuck permanently:

1. Worker crashes or is killed before `remove_active_worker()` is called -- the PID
   is never reaped by the supervisor's `ChildProcessError` path, which pops the
   supervisor-side dict but never calls `dashboard_state.remove_active_worker()`.
2. Pipeline restart -- new supervisor instance has empty `active_workers` so there
   is nothing to reap, but if the old server process was still alive the stale
   entries were in its `DashboardState`.

## Current State

The core fix is already implemented:

- `sweep_dead_workers()` in `dashboard_state.py` uses `os.kill(pid, 0)` to detect
  dead PIDs and reap them as failures with elapsed time from `start_time`.
- Called from `snapshot()` so every dashboard read auto-clears stale entries.
- `ChildProcessError` handling in `supervisor.py` calls
  `remove_active_worker(pid, "fail", 0.0, elapsed_s)` when `os.waitpid` fails.
- Tests exist for sweep_dead_workers: dead PID removal, alive PID retention,
  empty state no-op, TOCTOU race handling, and snapshot integration.

## Remaining Work

The backlog item is marked "Review Required". A coder agent should validate that
the existing implementation satisfies all acceptance criteria end-to-end:

- Dead PID sweep removes stale entries from snapshot output
- ChildProcessError path in supervisor properly cleans dashboard state
- Test coverage for `sweep_dead_workers` is comprehensive (not just mocked out)
- No regressions in existing test suite

## Key Files

| File | Role |
|------|------|
| `langgraph_pipeline/web/dashboard_state.py` | `sweep_dead_workers()` and `snapshot()` |
| `langgraph_pipeline/supervisor.py` | `_reap_finished_workers()` and `_reap_one_worker()` |
| `tests/langgraph/web/test_dashboard_state.py` | Test coverage for sweep logic |

## Design Decisions

- `os.kill(pid, 0)` is the POSIX portable way to test PID liveness without
  sending a signal; `OSError` means the process is gone or not ours.
- Sweeping in `snapshot()` keeps the fix in one place and requires no new
  threading or background tasks.
- Duration for dead-PID entries is computed from `start_time` stored in
  `WorkerInfo` so the completion record has accurate elapsed time.
- Outcome for swept entries is `"fail"` -- consistent with the crash path in
  `_reap_one_worker`.
