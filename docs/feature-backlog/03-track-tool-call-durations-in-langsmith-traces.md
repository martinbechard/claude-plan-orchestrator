# Track tool call durations in LangSmith traces

## Status: Completed

## Priority: Low

## Summary

Add per-tool-call wall-clock duration tracking to the LangSmith traces emitted by
`emit_tool_call_traces`. Currently, each `ToolCallRecord` stores only a human-readable
`HH:MM:SS` timestamp at the moment the `tool_use` block is received from the stream.
Child runs in LangSmith are created and immediately ended with no duration information,
so the timeline in LangSmith is meaningless for understanding which tool calls took the
most time.

The fix is to pair `tool_use` events with their corresponding `tool_result` events using
the `tool_use_id` field that Claude CLI's `stream-json` format includes in both. When a
`tool_result` block arrives (inside a `user` message), the elapsed time since the matching
`tool_use` block was received represents the actual tool execution wall-clock duration.
This duration should be stored on `ToolCallRecord` and passed to `child.end()` via the
`end_time` parameter when posting to LangSmith.

## 5 Whys Analysis

1. **Why do LangSmith tool call durations appear meaningless?** Because all child runs are
   created and ended in a tight loop inside `emit_tool_call_traces`, so their recorded
   duration reflects milliseconds of post-processing, not actual tool execution time.
2. **Why isn't actual tool execution time captured?** Because `ToolCallRecord` only stores
   a `timestamp` string at tool-call time; there is no corresponding end-time or elapsed
   duration field.
3. **Why isn't an end-time captured?** Because `stream_json_output` only records
   `tool_use` events; it does not currently track `tool_result` events that arrive in
   subsequent `user` messages.
4. **Why does this matter for observability?** Because duration per tool is the primary
   signal for identifying which tool calls are performance bottlenecks in a task
   execution — without it, LangSmith traces cannot be used to reason about where time is
   actually spent.
5. **Why can't we just approximate durations from consecutive timestamps?** Because
   consecutive `tool_use` timestamps reflect when Claude decided to call a tool, not when
   the previous tool returned — the gap includes both tool execution and Claude processing
   time, making it an unreliable proxy.

**Root Need:** Pair each `tool_use` event with its `tool_result` counterpart via
`tool_use_id` during streaming, compute the elapsed wall-clock time, and propagate that
duration into the LangSmith child run so that traces accurately reflect how long each
tool invocation actually took.

## Implementation Notes

- `stream_json_output` in `claude_cli.py` needs to track in-flight tool calls: when a
  `tool_use` block is seen, record `tool_use_id → datetime.now()` in a local dict.
- When a `user` message arrives containing `tool_result` blocks, match each result's
  `tool_use_id` to the recorded start time and compute elapsed seconds.
- Store the computed duration (float, seconds) as a new `duration_s` field on
  `ToolCallRecord` (optional, defaulting to `None` for text blocks).
- In `emit_tool_call_traces`, pass `end_time = start_time + timedelta(seconds=duration_s)`
  to `child.end()` so LangSmith renders accurate spans.
- The `ToolCallRecord` TypedDict gains one optional field: `duration_s: Optional[float]`.

## Source

Identified during codebase analysis of `langsmith.py` and `claude_cli.py`.
