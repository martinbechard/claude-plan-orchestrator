# Traces: tool calls (Read, Edit, Bash, etc.) not displayed in traces or timelines

## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


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




## 5 Whys Analysis

Title: Tool calls are invisible in trace timelines, breaking execution visibility
Clarity: 4/5

5 Whys:

1. **Why aren't tool calls visible in the trace timeline?**
   Because the `proxy_trace` route only fetches direct children of the root run via `proxy.get_children(root_run_id)`, which returns graph node runs (execute_plan, create_plan, etc.). Tool calls are grandchildren (children of graph nodes), so they never get fetched or rendered.

2. **Why are tool calls structured as grandchildren instead of direct children?**
   Because the execution model mirrors LangGraph's architecture: graph node invocations are children of the root run, and tool invocations (Read, Edit, Bash, etc.) are children of those graph nodes. This is a natural consequence of how the plan orchestrator instruments execution.

3. **Why was the fetch logic designed to stop at one level?**
   Because the initial implementation prioritized showing the high-level execution flow (which graph nodes ran, how long did each take?). Tool-level details were considered a secondary requirement, so the code was optimized for simplicity rather than completeness.

4. **Why do users need to see tool calls in the trace?**
   Because plan execution is **tool-driven** — the actual work happens via Read, Edit, Bash calls. Without visibility into which tools ran, in what order, and for how long, users cannot debug execution failures, understand performance bottlenecks, or analyze what the orchestrator actually did.

5. **Why is this tool-level visibility critical to the system's purpose?**
   Because this system's job is to make execution **auditable and debuggable**. If the trace is incomplete and hides the actual work (tool calls), then the trace system fails its core purpose: giving users confidence that their plans executed correctly and allowing them to diagnose what went wrong.

Root Need: Complete hierarchical visibility into plan execution — from root run through graph nodes down to individual tool calls — so users can fully understand, debug, and optimize orchestrated execution.

Summary: The system's trace feature is incomplete without tool-level visibility, making it impossible for users to debug execution or understand what work was actually performed.
