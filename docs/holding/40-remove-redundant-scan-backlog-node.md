# Remove redundant scan_backlog graph node — CLI always pre-scans

## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


## Status: Open

## Priority: Low

## Summary

The scan_backlog node is the graph entry point but it always short-circuits
with return {} because the CLI pre-scans the next item and passes it as
initial state. Every graph invocation pays the overhead of an extra node
(trace entry, state serialization) that does nothing.

## What scan_backlog does today

    if state.get("item_path"):
        return {}

The CLI (both sequential loop and supervisor) always sets item_path before
invoking the graph. scan_backlog never reaches its actual scanning code in
production. It only runs the scanning logic in tests that invoke the graph
without pre-scanning.

## Other nodes checked

- create_plan: short-circuits when plan already exists (legitimate resume)
- execute_plan: short-circuits when no plan_path (legitimate guard)
- No other nodes have wasteful short-circuits

## Fix

1. Remove scan_backlog from the graph nodes and edges.
2. Change the entry point to intake_analyze.
3. Move the has_items conditional edge to check item_path before invoking
   the graph (in the CLI loop), or add it as a conditional on intake_analyze.
4. Update tests that invoke the graph without pre-scanning to either
   pre-scan or test scan_backlog as a standalone function.
5. Keep the scan_backlog function available for direct use by tests or
   future callers, just don't register it as a graph node.

## Acceptance Criteria

- Is scan_backlog removed from the graph node list in graph.py?
  YES = pass, NO = fail
- Does the graph entry point start at intake_analyze?
  YES = pass, NO = fail
- Do traces for a normal pipeline run show no scan_backlog entry?
  YES = pass, NO = fail
- Do all existing tests pass? YES = pass, NO = fail
- Does the scan_backlog function still exist and work when called directly?
  YES = pass, NO = fail
