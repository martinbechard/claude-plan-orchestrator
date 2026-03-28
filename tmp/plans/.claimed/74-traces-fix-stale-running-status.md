# Traces: "RUNNING" status for items that finished long ago

## Summary

Items like "01-old-bug" and "01-bug" show RUNNING status even though they
completed or were abandoned. This happens when end_time is never set
(the start event was recorded but the end event was lost).

## Acceptance Criteria

- Are traces with no end_time that are older than 1 hour automatically
  marked as "Abandoned" or "Unknown" instead of "RUNNING"?
  YES = pass, NO = fail
- Does the status reflect reality: completed traces say SUCCESS/FAIL,
  actually running traces say RUNNING? YES = pass, NO = fail

## LangSmith Trace: 39d31e58-518c-4c5f-a25c-e6c76727dce5


## 5 Whys Analysis

Title: Stale RUNNING status masks task completion, breaking observability

Clarity: 4

5 Whys:

1. Why do items show RUNNING status when they're actually completed or abandoned?
   - Because the end_time field is never populated; the start event was recorded but the corresponding end event was lost or not emitted, so the system has no signal that the task finished.

2. Why aren't end events being recorded?
   - Because end events from the task execution layer (LangGraph/LangSmith) aren't being successfully captured and persisted into the traces database.

3. Why are end events missing from the data?
   - Because either the execution system doesn't reliably emit end events, the events are dropped during transmission/processing, or the process terminates before the end event can be written.

4. Why is this a user-facing problem that needs fixing?
   - Because users see old, completed tasks still marked as RUNNING, which obscures actual system state and makes it impossible to distinguish between legitimately-running tasks and stale/stuck ones.

5. Why does this distinction matter?
   - Because observability only has value if it's trustworthy; when status is unreliable, users can't confidently answer "what's actually happening right now?" or "which tasks need my attention?"—defeating the entire purpose of monitoring.

Root Need: Users need trustworthy, accurate task status so they can understand true system state and make informed decisions about which items require investigation or action.

Summary: Missing end events cause completed tasks to appear stuck in RUNNING status, eroding trust in the traces system as a reliable observability tool.
