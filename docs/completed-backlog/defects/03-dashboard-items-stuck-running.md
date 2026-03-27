# Dashboard: work items stuck in "running" state after pipeline restart

## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


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




## 5 Whys Analysis

Title: In-memory worker state becomes stale after pipeline restart, leaving "running" items orphaned in the dashboard

Clarity: 4

5 Whys:

1. Why do active workers remain stuck in "running" state after the dashboard loads?
   - Because `active_workers` is an in-memory dict that is never persisted to disk. When the pipeline restarts or the process ends, all state is lost, but tasks are never marked as completed or failed—they simply vanish from the system, except lingering entries may still appear if viewed shortly after restart.

2. Why was `active_workers` designed as a non-persisted, in-memory dict?
   - Because it was built to track only the current pipeline run's live workers in a simple, transient cache—the design assumed workers would always cleanly call `remove_active_worker()` when done, and that the cache would be garbage-collected when the process exits.

3. Why does the design not account for worker crashes or incomplete cleanup?
   - Because there is no automatic health check or reap mechanism. The system has no way to detect whether a PID that was marked "running" still exists; it blindly trusts that every running worker will eventually call the cleanup function.

4. Why is there no automatic reap mechanism built into the supervisor?
   - Because observability of *failed* worker state was not a design requirement—only successful completions trigger state cleanup. Crashes, signals, or hung processes are treated as edge cases rather than expected failure modes.

5. Why are edge-case failures (crashes, signals, hung processes) not treated as expected?
   - Because the system assumes the observer (human user, dashboard) will manually notice stuck items and act, rather than the system itself validating that internal state (what we think is running) matches actual operational state (what PIDs actually exist).

Root Need: Continuous reconciliation between internal state and actual process state, with automatic cleanup of orphaned workers regardless of how they exit.

Summary: The dashboard lacks automatic worker state reconciliation and failure recovery, leaving orphaned "running" entries that persist across restarts and outlive crashed processes.
