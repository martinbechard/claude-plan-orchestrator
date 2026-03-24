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

**Root trace creation — use `scan_backlog`, not `intake_analyze`:**
All item types (defect, feature, analysis) pass through `scan_backlog` as the true
pipeline entry point. `intake_analyze` is a pass-through for features (no Claude call),
so creating the root trace there would misrepresent the trace start time for the most
common item type. `scan_backlog` is the correct and consistent creation point for all
types.

**Persisting the trace ID in the item file:**
`PipelineState` is held in the LangGraph SQLite checkpoint and is not durable across
process restarts that lose the checkpoint. The root trace ID must also be written into
the backlog item's markdown file as a metadata line (e.g.
`## LangSmith Trace: <uuid>`) when the root `RunTree` is created. On pipeline restart,
`scan_backlog` reads this field — if present, it reconstructs the `RunTree` with the
existing ID (using `RunTree(id=existing_id, ...)`) rather than creating a new one,
ensuring all spans for the item stay under the same trace even across restarts or
quota-pause cycles.

**State field:**
Add `langsmith_root_run_id: Optional[str]` to `PipelineState`. Populated by
`scan_backlog` (from the item file if already present, or freshly generated), cleared
by `archive` after the root run is posted.

**`emit_tool_call_traces` signature change:**
Add optional `parent_run_id: Optional[str] = None` parameter. When provided, pass it
to `RunTree(parent_run_id=parent_run_id, ...)`.

**Lifecycle:**
- `scan_backlog`: create root `RunTree`, write ID to item file, store in state
- Each `emit_tool_call_traces` call: nest under root via `parent_run_id`
- `archive`: call `root_run.end(outputs={cost, tokens})` and `root_run.post()`; remove
  the `## LangSmith Trace:` line from the item file before archiving

**When tracing is inactive:**
`langsmith_root_run_id` remains None, no file writes occur, all existing behaviour
is unchanged.

**Relationship to other features:**
Feature 03 (tool call duration via `tool_use_id` pairing) gives accurate child span
durations; this feature provides the parent context that makes those durations
interpretable as a timeline.

## Source

Identified on 2026-03-24 during review of LangSmith tracing architecture. Confirmed
no `parent_run_id` threading exists anywhere in the codebase.
