# Quota exhaustion not detected in create_plan causes false archival of backlog items

## Status: Open

## Priority: High

## Summary

`detect_quota_exhaustion()` is only called inside `execute_task` (task_runner.py:481).
The `create_plan` and `intake_analyze` nodes also invoke Claude but have no quota
detection. When quota runs out during `create_plan`, the limit message is swallowed,
the node returns a partial or empty plan, and the pipeline continues to `execute_plan`.
By that point the quota message no longer appears in the Claude subprocess output, so
`quota_exhausted` is never set, and the feature routes through `is_defect()` directly
to `archive` — permanently losing the item from the backlog without any work done.

## Observed Incident

2026-03-24 ~12:36: features 04 (hot-reload) and 05 (periodic-progress-report) were
archived 3 seconds apart with no implementation commits. Both had been created in the
feature backlog minutes earlier. Item 03 (tool call duration tracking) was correctly
implemented just before them, exhausting the remaining quota. Items 04 and 05 then
flowed through create_plan → execute_plan → archive without detection.

## Root Cause

The quota detection guard exists only at the `execute_task` boundary. Nodes earlier in
the pipeline that call Claude (`intake_analyze`, `create_plan`) can absorb the quota
exhaustion signal without propagating it, leaving the pipeline state's `quota_exhausted`
field False when execution reaches the routing edge.

```
intake_analyze  → calls Claude, NO quota check
create_plan     → calls Claude, NO quota check
execute_plan
  └─ execute_task → calls Claude, quota check HERE (too late if prior nodes consumed signal)
is_defect() → quota_exhausted=False → NODE_ARCHIVE  ← item lost
```

## Fix

Add `detect_quota_exhaustion()` checks to `create_plan` and `intake_analyze`. When
detected, each node should return `{"quota_exhausted": True}` without advancing state,
and the routing edges from those nodes must short-circuit to END (leaving the item file
on disk for re-discovery). The graph topology needs conditional edges out of
`create_plan` and `intake_analyze` to handle the quota case, mirroring the existing
`is_defect()` guard on `execute_plan`.

Specifically:
- `intake_analyze` node: detect quota in Claude output, return `quota_exhausted=True`
- `create_plan` node: detect quota in Claude output, return `quota_exhausted=True`
- `pipeline/edges.py`: add `after_intake()` and `after_create_plan()` routing functions
  that check `quota_exhausted` and return END if set
- `pipeline/graph.py`: replace the fixed edges
  `intake_analyze → create_plan` and `create_plan → execute_plan` with conditional
  edges using the new routing functions

## Source

Root-caused on 2026-03-24 after observing features 04 and 05 falsely archived at 12:36
with no implementation commits despite the quota exhaustion feature being marked complete.
