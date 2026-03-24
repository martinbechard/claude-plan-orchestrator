# LangSmith Tool Call Tracing - Design

## Overview

Enhance the pipeline to emit LangSmith child runs for each tool call that Claude
makes during a task execution. Currently, task executions appear as opaque single
invocations in LangSmith. After this change, each tool call (Read, Edit, Write,
Bash, Grep, Glob, etc.) appears as a child span with its name, input, and timestamp.

## Approach

Post-hoc trace construction (Approach A from the backlog item). The
stream_json_output function already parses every event. We extend it to also
accumulate structured tool call records into a list. After the subprocess completes
and threads join, we iterate the collected events and emit LangSmith child runs
using the RunTree API.

## Architecture

```
stream_json_output()
  |-- parses tool_use events (existing)
  |-- appends ToolCallRecord to tool_calls list (new)
  |
_run_claude()
  |-- threads join
  |-- calls emit_tool_call_traces(tool_calls, result_capture) (new)
        |-- creates parent RunTree for the task
        |-- creates child RunTree per tool call
        |-- posts traces to LangSmith
```

## Key Changes

### 1. langgraph_pipeline/shared/claude_cli.py

- Define a ToolCallRecord TypedDict (tool_name, tool_input, timestamp)
- Add an optional tool_calls parameter (list) to stream_json_output
- When a tool_use block is parsed, append a ToolCallRecord to the list
- Also capture assistant text blocks into the list for completeness

### 2. langgraph_pipeline/shared/langsmith.py

- Add emit_tool_call_traces() function:
  - Takes the list of ToolCallRecords, parent run context, and task metadata
  - Creates child runs using the langsmith RunTree API
  - Gracefully degrades when langsmith is not installed or tracing is disabled

### 3. langgraph_pipeline/executor/nodes/task_runner.py

- Pass a tool_calls list into stream_json_output via _run_claude
- After threads join, call emit_tool_call_traces with the collected events
- Return tool_calls alongside the existing result_capture

## Design Decisions

1. Post-hoc over real-time: avoids thread-safety complexity with the LangSmith
   client. All RunTree construction happens on the main thread after join.

2. ToolCallRecord as TypedDict: lightweight, no class overhead, JSON-serializable.

3. Graceful degradation: if langsmith SDK is missing or tracing is disabled, the
   tool_calls list is simply never consumed. Zero overhead when tracing is off.

## Testing

- Unit tests for stream_json_output verify tool_calls accumulation
- Unit tests for emit_tool_call_traces verify RunTree construction (mocked)
- Existing task_runner tests should not regress since tool_calls is optional
