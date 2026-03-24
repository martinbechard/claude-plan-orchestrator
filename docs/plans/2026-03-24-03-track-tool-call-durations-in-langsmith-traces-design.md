# Design: Track Tool Call Durations in LangSmith Traces

## Status: Implementation Already Complete

Date: 2026-03-24
Source: docs/feature-backlog/03-track-tool-call-durations-in-langsmith-traces.md

## Architecture Overview

All changes described in the feature request are already present in the codebase.
The plan validates the existing implementation and closes the backlog item.

### Existing Implementation

**`langgraph_pipeline/shared/claude_cli.py`**

`ToolCallRecord` has the required optional fields:

```
tool_use_id: NotRequired[Optional[str]]
start_time:  NotRequired[Optional[datetime]]
duration_s:  NotRequired[Optional[float]]
```

`stream_json_output` maintains a `pending: dict[str, tuple[datetime, ToolCallRecord]]` map.
When a `tool_use` block arrives, `start_time` is captured and an entry is added to `pending`.
When a `user` message carrying `tool_result` blocks arrives, each result's `tool_use_id` is
looked up in `pending`; the elapsed wall-clock time is computed and stored as `duration_s`
on the matching record.

**`langgraph_pipeline/shared/langsmith.py`**

`emit_tool_call_traces` reads `duration_s` and `start_time` from each `ToolCallRecord`.
When both are present, it computes `end_time = start_time + timedelta(seconds=duration_s)`
and passes it to `child.end(end_time=end_time)`, so LangSmith renders accurate span widths.

**`tests/langgraph/shared/test_claude_cli.py`**

`TestStreamJsonOutputDurationTracking` covers:
- `duration_s` is set when a matching `tool_result` arrives
- `duration_s` is absent for text blocks
- `duration_s` is absent for unmatched tool calls (no `tool_result` received)
- `start_time` is captured on the `ToolCallRecord`
- `tool_use_id` is stored correctly
- Unmatched `tool_result` blocks are silently ignored

## Key Files

| File | Role |
|------|------|
| `langgraph_pipeline/shared/claude_cli.py` | `ToolCallRecord` type + `stream_json_output` streaming |
| `langgraph_pipeline/shared/langsmith.py` | `emit_tool_call_traces` uses `duration_s` for LangSmith spans |
| `tests/langgraph/shared/test_claude_cli.py` | Duration-tracking unit tests |
| `tests/langgraph/shared/test_langsmith.py` | `emit_tool_call_traces` unit tests |

## Design Decisions

- Duration is wall-clock elapsed time (Python `datetime.now()` difference) between the
  moment the `tool_use` block is received from the stream and the moment the matching
  `tool_result` arrives in a subsequent `user` message.
- `duration_s` is an optional float (seconds). Records without a matched result leave
  the field absent rather than `0`, avoiding misleading zero-duration spans.
- The `pending` dict lives inside `stream_json_output` as a local variable — no shared
  state escapes the function boundary.
- `emit_tool_call_traces` degrades gracefully: if either `duration_s` or `start_time` is
  absent, `child.end()` is called without `end_time`.
