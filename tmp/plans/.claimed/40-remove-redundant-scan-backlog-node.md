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

## LangSmith Trace: 3febf02c-209a-45c1-86d7-c0cdce7e6213


## 5 Whys Analysis

Title: Remove redundant scan_backlog node that always short-circuits in production

Clarity: 4

5 Whys:

1. **Why is scan_backlog considered redundant?** Because the CLI (sequential loop and supervisor) always pre-scans the next item and passes `item_path` as initial state, so `scan_backlog` immediately returns `{}` without executing its actual scanning logic in production.

2. **Why does the CLI pre-scan instead of letting the graph scan?** Because the orchestrator needs to determine what item to work on next before invoking the graph, requiring the scan to happen at the loop level so a valid `item_path` can be passed as initial state.

3. **Why was scan_backlog designed as a graph node if it never runs in production?** To maintain scanning logic within the graph for reusability and testability—allowing tests to invoke the graph without pre-scanning while letting production callers short-circuit via pre-scan, rather than having two separate code paths.

4. **Why remove this inefficiency now rather than accept the extra node?** Because every graph invocation pays tracing overhead (serialization, state setup, logging), and multiplying that cost across hundreds of pipeline orchestration cycles wastes measurable resources while adding no value.

5. **Why does this architectural misalignment matter if it still works?** Because a node that never executes in production confuses the graph's contract (is the entry point `scan_backlog` or `intake_analyze`?), creates maintenance burden, and obscures what actually needs to be tested and optimized in traces.

Root Need: **Align the graph's documented architecture with its actual runtime behavior by removing the production-unused entry point, reducing per-invocation overhead, and clarifying the true entry point for future maintainers and performance analysis.**

Summary: Remove scan_backlog from the graph because CLI pre-scanning makes it a permanent no-op that wastes invocation overhead and contradicts the actual system design.
