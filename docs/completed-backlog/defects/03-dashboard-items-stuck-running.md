# Dashboard: work items stuck in "running" state after pipeline restart

## Status: Open

## Priority: High

## Summary

The Active Workers panel in the dashboard shows items permanently stuck in
"running" state. This happens because `DashboardState.active_workers` is an
in-memory dict that is never persisted. When the pipeline restarts, workers
that were running before the restart are never reaped, so their entries
disappear from memory. However, if the web server and pipeline share a process,
or if the dashboard is viewed shortly after restart, stale in-flight entries
from the previous run may linger.

A second cause: if a worker process crashes or is killed before calling
`remove_active_worker()`, its entry stays in `active_workers` forever for the
lifetime of that pipeline run.

## Observed Behavior

- The Active Workers panel shows one or more items with large elapsed times
  that never complete.
- Refreshing the dashboard does not clear them.

## Root Cause

`active_workers` is a plain dict in `DashboardState`. There is no timeout or
reap-on-missing-pid logic. Crashed workers are never removed.

## Expected Behavior

Active workers whose PIDs are no longer running should be automatically reaped
as "fail" completions with the actual elapsed time.

## Suggested Fix

In the `supervisor.py` reap loop, after calling `os.waitpid` or detecting a
missing process, always call `dashboard_state.remove_active_worker()` — even
on the crash/signal path. Additionally, add a periodic sweep in
`DashboardState.snapshot()` or in the supervisor that checks each PID in
`active_workers` with `os.kill(pid, 0)` and removes entries for dead processes.
