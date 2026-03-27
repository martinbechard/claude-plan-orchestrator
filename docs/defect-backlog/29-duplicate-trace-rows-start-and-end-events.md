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

## LangSmith Trace: 967632e3-75a5-41ab-9266-868e68949d49


## 5 Whys Analysis

**Title:** Duplicate trace rows prevent readable timeline view of pipeline execution

**Clarity:** 4

**5 Whys:**

1. **Why are pipeline steps appearing twice on the trace detail page?**
   Because the TracingProxy.record_run() method executes a plain INSERT for every SDK trace event, and the LangGraph SDK emits two events per node—one at start (with end_time=NULL) and one at completion (with end_time and outputs populated).

2. **Why does the SDK emit two events per node instead of one?**
   Because LangSmith's event model captures both state transitions: the node's creation/start in the execution tree and its completion with results. This dual-event pattern allows real-time monitoring of in-progress nodes while they execute.

3. **Why does the current code insert both events as separate rows instead of merging them?**
   Because TracingProxy.record_run() uses INSERT without an upsert (INSERT OR REPLACE) pattern, so it has no mechanism to detect "this run_id already exists, update it instead of inserting again." It treats each event as a new row.

4. **Why wasn't the upsert pattern implemented initially?**
   Because the developer likely didn't anticipate or catch the double-event pattern during initial development, treating the SDK output as a one-event-per-node model rather than designing for the SDK's actual event emission strategy.

5. **Why does showing duplicate rows make the timeline unreadable for users?**
   Because the visual representation becomes 2x cluttered—users see two nearly-identical rows per step, making it harder to scan the sequence, identify logical steps, and understand overall pipeline flow and timing.

**Root Need:** Enable users to understand pipeline execution flow clearly by showing exactly one logical timeline entry per node, updated with completion data when available, without visual duplication that obscures the execution sequence.

**Summary:** The root need is to display an accurate, non-duplicated node timeline so users can easily trace execution flow and identify which step is currently running or has failed.
