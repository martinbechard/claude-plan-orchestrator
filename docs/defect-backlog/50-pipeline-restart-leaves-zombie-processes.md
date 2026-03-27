# Pipeline restart leaves zombie processes causing duplicate workers and empty dashboard

## Summary

When restarting the pipeline (kill + start), the old process often survives
and both instances run simultaneously. This causes: duplicate workers
claiming the same items, DashboardState split across two processes (one
shows 0 workers), and duplicate completions.

## Acceptance Criteria

- After sending SIGTERM and starting a new pipeline, is the old process
  fully dead? Check: only 1 langgraph_pipeline.cli process running.
  YES = pass, NO = fail
- Does the startup code verify no other pipeline instance is running
  and kill it if found (using the PID file)? YES = pass, NO = fail
- Does the PID file get updated atomically so there's no window where
  two instances think they own it? YES = pass, NO = fail
- Are all child worker processes killed when the parent is killed?
  YES = pass, NO = fail
