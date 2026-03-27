# Trace detail: every node appears twice (start event + end event stored as separate rows)

## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


## Status: Open

## Priority: High

## Summary

The trace detail page shows each pipeline step duplicated (two intake_analyze,
two create_plan, two verify_symptoms, etc.). This makes the timeline
unreadable. The cause is that the LangGraph/LangSmith SDK sends two trace
events per node — one when the node starts (end_time is NULL) and one when
it completes (end_time is populated) — and both are stored as separate rows
in the traces table with the same run_id.

## Evidence

    SELECT run_id, name, start_time, end_time
    FROM traces WHERE parent_run_id = '019d2b76-79f4-79b3-abfd-6a6536f5c788'
    ORDER BY start_time;

    -- intake_analyze appears twice with same run_id and start_time:
    019d2b76-7a30...|intake_analyze|18:44:38.064|NULL
    019d2b76-7a30...|intake_analyze|18:44:38.064|18:44:46.178

    -- Same pattern for create_plan, verify_symptoms, etc.

## Root Cause

The TracingProxy.record_run() method does an INSERT for every call. The SDK
calls record_run once at node start (end_time=NULL, outputs=NULL) and again
at node completion (with end_time and outputs). This produces two rows per
node instead of one row that gets updated.

## Fix

In TracingProxy.record_run(), use INSERT OR REPLACE (upsert) keyed on
run_id instead of a plain INSERT:

    INSERT INTO traces (run_id, ...) VALUES (...)
    ON CONFLICT(run_id) DO UPDATE SET
      end_time = excluded.end_time,
      outputs_json = excluded.outputs_json,
      error = excluded.error

This requires adding a UNIQUE constraint on the run_id column. The end
result: one row per node, updated in place when the completion event arrives.

Alternatively, the proxy list/detail queries could filter to only show
rows WHERE end_time IS NOT NULL (completed events), but this would hide
currently-running nodes. The upsert approach is cleaner.
