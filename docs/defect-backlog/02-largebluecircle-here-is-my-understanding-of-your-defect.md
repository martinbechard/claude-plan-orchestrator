# :large_blue_circle: *Here is my understanding of your defect:*

## Status: Open

## Priority: Medium

## Summary

`★ Insight ─────────────────────────────────────`
This is a classic observability gap: the streaming parser was built for real-time display, not for constructing trace spans. The fix requires event correlation (pairing tool_use with tool_result), which is a fundamentally different data model than single-event capture.
`─────────────────────────────────────────────────`

**Title:** Compute tool call duration from paired start/end timestamps instead of defaulting to zero

**Classification:** defect - Tool call child runs in LangSmith all show 0.00s duration because timing data is never captured or passed to RunTree.

**5 Whys:**
1. **Why do LangSmith child runs show 0.00s duration?** Because `emit_tool_call_traces()` calls `child.end()` without passing `start_time`/`end_time` arguments, so LangSmith defaults to zero duration.
2. **Why doesn't `emit_tool_call_traces()` pass timing information?** Because `ToolCallRecord` only contains a single `timestamp` field (observation time) with no end-time or duration, so there's nothing meaningful to pass.
3. **Why does `ToolCallRecord` lack an end timestamp?** Because `stream_json_output()` captures tool_use events independently but never captures the corresponding tool_result events that would provide the completion time.
4. **Why aren't tool_result events correlated with their originating tool_use events?** Because the streaming parser processes each JSON event in isolation for live progress display, with no state machine to pair request/response events into complete spans.
5. **Why was there no event-pairing state machine in the streaming parser?** Because LangSmith integration was added after the streaming infrastructure was built for real-time display, and the data model was never extended to support the paired start/end events needed for accurate duration computation.

**Root Need:** Tool call durations must be derived from paired start/end timestamps (the single source of truth), not from an independent field that silently defaults to zero.

**Description:**
Extend `stream_json_output()` to correlate tool_use events with their corresponding tool_result events, capturing both start and end timestamps. Add `end_timestamp` to `ToolCallRecord` and pass `start_time`/`end_time` to each `RunTree.create_child()` call in `emit_tool_call_traces()`. This ensures duration is always computed from authoritative timestamp data rather than defaulting to zero.

## Source

Created from Slack message by U0AFA7SAEMC at 1774329959.769549.
