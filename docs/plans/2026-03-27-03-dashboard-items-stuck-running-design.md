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

## Current State

The core fix is already implemented:

- `sweep_dead_workers()` in `dashboard_state.py` (lines 222-245) uses `os.kill(pid, 0)`
  to detect dead PIDs and reap them as failures with elapsed time from `start_time`.
- Called from `snapshot()` (line 260) so every dashboard read auto-clears stale entries.
- `ChildProcessError` handling in `supervisor.py` (lines 485-491) calls
  `remove_active_worker(pid, "fail", 0.0, elapsed_s)` when `os.waitpid` fails.

## Remaining Work

Validate acceptance criteria from the work item. The implementation exists but needs
verification that all paths work correctly and tests cover the key scenarios:

- Dead PID sweep removes stale entries from snapshot
- ChildProcessError path in supervisor properly cleans dashboard state
- Test coverage for `sweep_dead_workers` directly (not just mocked out)

## Key Files

| File | Change |
|------|--------|
| `langgraph_pipeline/web/dashboard_state.py` | Has `sweep_dead_workers()` — verify correctness |
| `langgraph_pipeline/supervisor.py` | Has `ChildProcessError` fix — verify correctness |
| `tests/langgraph/web/test_dashboard_state.py` | Verify/add test coverage for sweep logic |

## Design Decisions

- `os.kill(pid, 0)` is the POSIX portable way to test PID liveness without
  sending a signal; `OSError` means the process is gone or not ours.
- Sweeping in `snapshot()` keeps the fix in one place and requires no new
  threading or background tasks.
- Duration for dead-PID entries is computed from `start_time` stored in
  `WorkerInfo` so the completion record has accurate elapsed time.
- Outcome for swept entries is `"fail"` — consistent with the crash path in
  `_reap_one_worker`.
