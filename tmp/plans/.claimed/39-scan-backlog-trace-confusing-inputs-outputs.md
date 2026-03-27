# scan_backlog trace: inputs show pre-populated item, outputs are empty

## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


## Status: Open

## Priority: Low

## Summary

When viewing a scan_backlog trace, the inputs show a fully populated work
item (item_path, item_slug, item_type already set) and the outputs are {}.
This is confusing because scan_backlog's job is to FIND the next item, so
the inputs should be empty and the outputs should contain the found item.

## Root Cause

The CLI pre-scans the backlog before invoking the graph and passes the
found item as initial state. When scan_backlog runs, it sees item_path
already populated and short-circuits (returns {}). So the trace accurately
reflects what happened — but it looks backwards to anyone reading the trace.

The LangGraph SDK logs the full graph state as "inputs" to every node,
not just the node's actual inputs. So scan_backlog appears to receive the
item it was supposed to find.

## Suggested Fix

This is a trace readability issue, not a functional bug. Options:

1. In the trace detail UI, label node inputs as "State before" and outputs
   as "State changes" to make the LangGraph convention clearer.
2. Add a note in scan_backlog's trace metadata indicating "short-circuited:
   item already pre-scanned by CLI" so the viewer understands why inputs
   are populated and outputs are empty.
3. In the trace detail page, hide empty outputs ({}) rather than showing
   an "Outputs" section with just {}.

## LangSmith Trace: 4a9b5230-68b7-4088-b059-b7d48ed19c38
