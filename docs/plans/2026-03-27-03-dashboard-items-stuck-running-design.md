# Design: Dashboard Items Stuck in Running State

## Work Item

tmp/plans/.claimed/03-dashboard-items-stuck-running.md

## Status: Review Required

This defect was previously implemented. The fix needs verification and any
gaps need to be addressed.

## Architecture Overview

The dashboard tracks active workers via an in-memory dict in
DashboardState.active_workers (keyed by PID). Workers that crash or whose
processes disappear without calling remove_active_worker() leave stale
entries.

The existing fix adds sweep_dead_workers() which probes each PID with
os.kill(pid, 0) and reaps dead entries as failures. This is called at the
top of snapshot() so every dashboard refresh cleans up zombies.

## Key Files

### Already Modified (verify)

- langgraph_pipeline/web/dashboard_state.py
  - sweep_dead_workers() method (lines 222-245)
  - Called from snapshot() at line 260
  - Probes PIDs with os.kill(pid, 0), reaps dead ones as "fail"

- langgraph_pipeline/supervisor.py
  - _reap_finished_workers() handles ChildProcessError (lines 485-491)
  - _reap_one_worker() calls remove_active_worker on crash path (line 361)

### Test Coverage Gap

- tests/langgraph/web/test_dashboard_state.py
  - Missing: dedicated tests for sweep_dead_workers()
  - Missing: test that snapshot() calls sweep before returning
  - Missing: test for already-reaped PID in supervisor path

## Design Decisions

1. The sweep approach (os.kill probe) is correct for this architecture
   since workers are OS child processes with known PIDs.

2. Calling sweep from snapshot() ensures the dashboard never shows stale
   entries regardless of how the worker died.

3. The supervisor ChildProcessError handler is a belt-and-suspenders
   guard for the case where waitpid fails because the child was already
   reaped by another thread.

## Verification Focus

- Confirm sweep_dead_workers reaps entries for dead PIDs
- Confirm snapshot() calls sweep_dead_workers before building the response
- Confirm supervisor handles ChildProcessError and removes dashboard entry
- Add unit tests for sweep_dead_workers edge cases
