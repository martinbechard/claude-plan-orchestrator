# Design: Remove Redundant scan_backlog Graph Node

## Problem

The scan_backlog node is the graph entry point but always short-circuits with
return {} because the CLI pre-scans the next item and passes it as initial state.
Every graph invocation pays unnecessary overhead (trace entry, state serialization)
for a node that does nothing in production.

## Architecture Change

### Current Flow

```
CLI pre-scans item -> graph starts at scan_backlog -> scan_backlog returns {} -> intake_analyze -> ...
```

### New Flow

```
CLI pre-scans item -> graph starts at intake_analyze -> ...
```

## Key Files to Modify

- Graph definition file (where nodes and edges are registered) - remove scan_backlog
  as a node, change entry point to intake_analyze
- CLI loop / supervisor - ensure has_items check happens before graph invocation
  if it was previously handled as a conditional edge from scan_backlog
- Tests - update any tests that invoke the graph without pre-scanning to either
  pre-scan or test scan_backlog as a standalone function

## Key Files to Preserve

- The scan_backlog function itself - keep it available for direct use by tests or
  future callers, just remove it from the graph registration

## Design Decisions

1. Keep scan_backlog function: The function remains available for direct invocation.
   Only the graph node registration is removed.
2. Entry point change: intake_analyze becomes the new graph entry point.
3. Conditional edge migration: Any has_items conditional edge on scan_backlog moves
   to either the CLI loop or a conditional on intake_analyze.
4. Test updates: Tests that relied on scan_backlog being a graph node get updated
   to either pre-scan or call scan_backlog directly.


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
