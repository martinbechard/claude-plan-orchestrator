# LangSmith Tool Call Tracing from Streamed Claude CLI Output

## Status: Open

## Priority: Medium

## Summary

When the executor runs Claude CLI tasks via subprocess, tool calls (Read, Edit, Write, Bash, Grep, Glob) are streamed in real-time via stream-json format but are not logged to LangSmith. This means LangSmith traces show the task as a single opaque invocation with no visibility into what Claude did during execution.

## Current Behavior

The task runner in executor/nodes/task_runner.py spawns Claude CLI with --output-format stream-json. The stream_json_output function in shared/claude_cli.py parses events in real-time (assistant text blocks, tool_use blocks, result events) and prints summaries to stdout. But none of this data is sent to LangSmith.

The result event at the end contains cost and token counts, which ARE captured in result_capture and logged via add_trace_metadata. But the individual tool calls within the task are invisible in LangSmith.

## Expected Behavior

Each Claude CLI task execution should produce a LangSmith trace that includes:

1. The task prompt (already available as the prompt argument)
2. Individual tool calls as child spans/runs:
   - Tool name (Read, Edit, Write, Bash, Grep, Glob, etc.)
   - Tool input (file_path, command, pattern, etc.)
   - Timestamp
3. Assistant text blocks as intermediate outputs
4. The final result with cost/token metadata (already captured)

This would allow debugging failed tasks by inspecting exactly what Claude did in the LangSmith dashboard.

## Implementation Approach

The stream_json_output function already parses every event from the Claude CLI stream. The enhancement is to also emit these as LangSmith child runs.

Two approaches to consider:

### Approach A: Post-hoc trace construction
After the CLI subprocess completes, iterate over the collected events and construct a LangSmith trace tree using the langsmith SDK's RunTree API. This avoids real-time coordination with the streaming thread but means traces appear only after task completion.

### Approach B: Real-time child run creation
During streaming, create LangSmith child runs for each tool_use event as they arrive. This gives live visibility but requires thread-safe interaction with the LangSmith client from the streaming thread.

### Recommendation
Approach A (post-hoc) is simpler and lower-risk. The stream_json_output function already captures events in result_capture. Extend it to also accumulate a list of tool call events, then after the subprocess completes and threads join, emit the full trace tree to LangSmith.

## Key Files

- langgraph_pipeline/shared/claude_cli.py -- stream_json_output function (event parsing)
- langgraph_pipeline/executor/nodes/task_runner.py -- execute_task node (subprocess management)
- langgraph_pipeline/shared/langsmith.py -- tracing utilities (add_trace_metadata)

## Dependencies

- LangSmith must be enabled (langsmith.enabled: true) and configured
- Requires the langsmith Python SDK for RunTree API
