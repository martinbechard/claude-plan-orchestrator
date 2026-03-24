# LangSmith per-item root trace for cross-step aggregation

## Status: Open

## Priority: Low

## Summary

Every call to `emit_tool_call_traces` creates an independent `RunTree` with no
`parent_run_id`. All tool call spans for a given work item (across intake, plan
creation, and every task execution step) are emitted as disconnected top-level
traces in LangSmith. There is no way to view the full execution of one backlog item
as a single aggregated trace. Adding a shared root `RunTree` per work item — created
when the item enters the pipeline and passed through to every `emit_tool_call_traces`
call — would group all spans under one trace, enabling end-to-end latency, cost, and
token views per item in LangSmith.

## 5 Whys Analysis

1. **Why can't you see a work item's full execution in one LangSmith trace?** Because
   each `emit_tool_call_traces` call constructs a new `RunTree()` with no
   `parent_run_id`, making every call a separate top-level trace.
2. **Why wasn't a shared root trace threaded through?** The initial LangSmith
   integration focused on capturing tool call events; cross-step aggregation was not
   part of the original scope.
3. **Why does this matter?** Without a root trace, LangSmith cannot show total cost,
   total tokens, or end-to-end latency for a single work item — the most useful
   unit for understanding pipeline performance and debugging failures.
4. **Why not just correlate by metadata?** `plan_name` and `task_id` are attached as
   metadata to each trace, but LangSmith's UI groups by trace hierarchy, not by
   metadata fields — correlation by metadata requires manual filtering and cannot
   produce a unified timeline view.
5. **Why is this also a prerequisite for duration tracking?** Per-tool durations
   (feature 03) are only meaningful in context when the spans are nested under a
   shared root that shows where each task sits within the overall item execution.

**Root Need:** Create one root `RunTree` per backlog item at pipeline entry and pass
its ID as `parent_run_id` to every `emit_tool_call_traces` call for that item, so
LangSmith aggregates all tool calls, task steps, and costs under a single trace.

## Implementation Notes

- Create the root `RunTree` in the `intake_analyze` or `scan_backlog` node when a
  new item is picked up; store its `id` in `PipelineState` (new field:
  `langsmith_root_run_id: Optional[str]`).
- Pass `parent_run_id=root_run_id` to `RunTree(...)` inside `emit_tool_call_traces`;
  add an optional `parent_run_id` parameter to `emit_tool_call_traces`.
- Call `root_run.end()` and `root_run.post()` in the `archive` node after the item
  is fully processed, so LangSmith records the total wall-clock duration.
- The root run's `inputs` should carry item metadata (item type, slug, plan name);
  its `outputs` should carry final cost and token totals from `PipelineState`.
- When `_tracing_active` is False, `langsmith_root_run_id` remains None and all
  existing behaviour is unchanged.
- This feature and feature 03 (tool call duration tracking via `tool_use_id` pairing)
  are complementary: 03 gives accurate child span durations; this feature gives the
  parent context that makes those durations interpretable.

## Source

Identified on 2026-03-24 during review of LangSmith tracing architecture. Confirmed
no `parent_run_id` threading exists anywhere in the codebase.
