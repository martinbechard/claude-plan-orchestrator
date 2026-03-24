# Defect Fix: Calculate Tool Call Duration from Timestamps - Design

## Overview

Tool call durations appear as 0.00 seconds in LangSmith because `emit_tool_call_traces`
creates child runs in a tight loop with no timing information. Each `ToolCallRecord`
currently stores only a human-readable `HH:MM:SS` string at the moment the `tool_use`
block is received; there is no end-time or elapsed duration.

The fix pairs each `tool_use` event with its corresponding `tool_result` event via the
`tool_use_id` field present in both. Elapsed wall-clock time between the two events
represents actual tool execution time. This duration is stored on `ToolCallRecord` and
propagated into the `end_time` parameter of `child.end()` in LangSmith.

## Architecture

```
stream_json_output()
  |-- sees tool_use block: record tool_use_id -> datetime.now() in pending dict
  |-- sees tool_result block (in user message): compute duration, update ToolCallRecord
  |
emit_tool_call_traces()
  |-- for each record: pass start_time + timedelta(seconds=duration_s) as end_time
  |-- child.end(outputs=..., end_time=...) -> LangSmith renders real span widths
```

## Key Files

### langgraph_pipeline/shared/claude_cli.py

- `ToolCallRecord` TypedDict gains two new optional fields:
  - `tool_use_id: Optional[str]` - the ID correlating tool_use to tool_result
  - `duration_s: Optional[float]` - computed elapsed seconds; None for text blocks
- `stream_json_output` gains an in-flight tracking dict (`pending: dict[str, datetime]`):
  - On `tool_use` block: add `tool_use_id -> datetime.now()` to pending
  - On `user` message with `tool_result` blocks: match `tool_use_id`, compute
    `(datetime.now() - start).total_seconds()`, update the matching record's `duration_s`

### langgraph_pipeline/shared/langsmith.py

- `emit_tool_call_traces` uses `duration_s` when present:
  - Reconstruct `start_time` from the record's timestamp (or use a running cursor)
  - Compute `end_time = start_time + timedelta(seconds=duration_s)`
  - Pass `end_time=end_time` to `child.end()`

## Design Decisions

1. **`tool_use_id` as correlation key**: The Claude CLI `stream-json` format includes
   `tool_use_id` in both `tool_use` (assistant message) and `tool_result` (user message)
   blocks. This is the only reliable way to pair calls with results.

2. **Optional field, not required**: `duration_s` is `Optional[float]` and defaults to
   `None` for text blocks and any tool call whose result event was not captured. This
   preserves backward compatibility and graceful degradation.

3. **datetime for start_time**: The existing `timestamp: str` is kept for display.
   A new `start_time: datetime` field on `ToolCallRecord` replaces the need to parse
   the string back. The `pending` dict stores raw datetimes, which are also attached to
   the record for use in `emit_tool_call_traces`.

4. **No approximation via consecutive timestamps**: Consecutive `tool_use` timestamps
   conflate tool execution time with Claude processing time, making them unreliable.
   The `tool_result` pairing approach is the only accurate measure.

## Testing

- Unit tests in `tests/langgraph/shared/test_claude_cli.py` verify:
  - `stream_json_output` computes `duration_s` when a matching `tool_result` arrives
  - `duration_s` is None for text blocks and unmatched tool calls
- Unit tests in `tests/langgraph/shared/test_langsmith.py` verify:
  - `emit_tool_call_traces` passes `end_time` to `child.end()` when `duration_s` is set
  - Missing `duration_s` falls back to the current behavior (no `end_time` arg)
