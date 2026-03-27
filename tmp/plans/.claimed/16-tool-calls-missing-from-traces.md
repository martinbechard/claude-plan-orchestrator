# Traces: tool calls (Read, Edit, Bash, etc.) not displayed in traces or timelines

## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


## Status: Open

## Priority: High

## Summary

Claude Code tool invocations (Read, Edit, Write, Bash, Glob, Grep, Skill) are
stored in the traces DB as child runs but are not visible in the trace detail
timeline or anywhere in the UI. The timeline only shows LangGraph graph node
runs (scan_backlog, execute_plan, etc.) because get_children() only returns
direct children of the root run.

## Evidence

The DB contains tool call rows:

    SELECT DISTINCT name FROM traces WHERE parent_run_id IS NOT NULL;
    → Bash, Edit, Glob, Grep, Read, Skill, Write, ...

But these are grandchildren (children of graph node runs), not direct children
of the root run. The route calls proxy.get_children(run_id) with only the root
run_id, so tool calls nested under graph nodes never appear.

## Root Cause

The trace detail route (proxy.py proxy_trace) fetches only one level of
children:

    children = proxy.get_children(run_id)

Tool calls like Read, Edit, Bash are children of graph node runs (e.g.
execute_plan, create_plan), making them grandchildren of the root. They are
never fetched or displayed.

## Expected Behavior

- The trace detail page should show tool calls nested under their parent
  graph node.
- The timeline should display tool calls as bars within their parent node's
  time span.
- Tool calls should be visually distinguishable (per defect 13 colour fix).

## Fix

This overlaps with defect 04/08 (expandable items in timeline):

1. In proxy_trace route, fetch grandchildren: for each child that has
   sub-children, call proxy.get_children(child.run_id) and pass
   grandchildren_by_parent dict to the template.
2. In the timeline SVG, render grandchildren as indented/nested bars under
   their parent graph node bar (or use the expandable HTML detail approach
   from defect 04).
3. In the runs detail section below the timeline, show tool calls under
   their parent graph node using details/summary toggle.

## Dependencies

- Defect 04/08: expandable timeline items (same infrastructure needed)
- Defect 13: bar colour classification (tool calls need distinct colour)

## LangSmith Trace: 69e284fb-f4ab-4fb5-9d7a-f97e277c3623
