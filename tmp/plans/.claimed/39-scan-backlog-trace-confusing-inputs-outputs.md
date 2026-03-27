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


## 5 Whys Analysis

Title: Trace readability obscures pre-scanning behavior that developers need to understand for debugging
Clarity: 4/5

5 Whys:
1. Why does the scan_backlog trace look confusing to viewers?
   Because inputs show a fully populated item and outputs show {}, which appears backwards from scan_backlog's responsibility of finding the next item.

2. Why do the inputs show the item that scan_backlog was supposed to find?
   Because the LangGraph SDK logs the full graph state at each node as "inputs," not just what the node actually receives as input; the CLI had already pre-scanned the backlog and populated that item in state before invoking the graph.

3. Why does the CLI pre-scan and populate the item before the graph runs?
   To optimize execution: if an item is already found during pre-scan, the graph can short-circuit without repeating the scan operation, saving compute and time.

4. Why do developers need to understand this pre-scanning optimization when reading traces?
   Because they need to distinguish between "scan_backlog ran and found nothing" (empty outputs from normal operation) versus "scan_backlog short-circuited because the CLI pre-scanned" (empty outputs from optimization), which have different implications for debugging.

5. Why does the distinction matter if both paths produce correct results?
   Because without understanding the optimization, developers might misinterpret the trace as a failure or unexpected behavior, creating debugging friction and reducing confidence in observability—making the system harder to maintain and troubleshoot.

Root Need: **Developer mental models of node behavior must align with what traces actually show, so optimization decisions are visible and don't create false signals during debugging.**

Summary: This is a communication problem between the system's actual behavior (pre-scanning optimization) and what traces convey to developers trying to understand execution flow.
