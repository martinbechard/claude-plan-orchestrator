# Planner Targets Legacy Script Instead of LangGraph Pipeline — Design

## Problem

Feature 12 (structured execution cost log) was implemented in
`scripts/plan-orchestrator.py`, which is the legacy execution path. The active
execution path is `langgraph_pipeline/executor/nodes/task_runner.py`. As a
result, `docs/reports/execution-costs/` is never written during live pipeline
runs.

## Architecture Overview

The fix has two parts:

1. **Port the cost log to the LangGraph shared layer** — Create
   `langgraph_pipeline/shared/cost_log.py` with `write_execution_cost_log()`,
   add `COST_LOG_DIR` to `langgraph_pipeline/shared/paths.py`, and wire the
   call into `execute_task()` in `task_runner.py`.

2. **Guard against recurrence** — Add a note to `CLAUDE.md` stating that
   `scripts/plan-orchestrator.py` is legacy and all new pipeline features must
   go in `langgraph_pipeline/`.

## Key Files to Create / Modify

| File | Action |
|---|---|
| `langgraph_pipeline/shared/paths.py` | Add `COST_LOG_DIR` constant |
| `langgraph_pipeline/shared/cost_log.py` | Create — contains `write_execution_cost_log()` |
| `langgraph_pipeline/executor/nodes/task_runner.py` | Import and call `write_execution_cost_log()` after `emit_tool_call_traces()` |
| `CLAUDE.md` | Add note that `scripts/plan-orchestrator.py` is legacy |

## Design Decisions

### New shared module vs. inline in task_runner

`write_execution_cost_log()` is pure I/O logic with no dependency on LangGraph
state. Placing it in `langgraph_pipeline/shared/cost_log.py` keeps
`task_runner.py` focused on orchestration and mirrors the existing pattern
(`quota.py`, `langsmith.py`, etc. each own one concern).

### ToolCallRecord adaptation

The LangGraph `ToolCallRecord` (TypedDict in `claude_cli.py`) stores tool call
details differently from the legacy dataclass:

- `tool_name` → legacy `tool`
- `tool_input["file_path"]` → legacy `file_path` (for Read/Edit/Write/Grep/Glob)
- `tool_input["command"]` → legacy `command` (for Bash)
- `result_bytes` is not tracked in the LangGraph version; the field is omitted

`cost_log.py` converts each `ToolCallRecord` TypedDict to the same JSON shape
written by the legacy script, omitting `result_bytes`.

### Call site in execute_task

The call is placed after `emit_tool_call_traces()` and before the final
`interrupt()` check so the log is written regardless of suspension status.
Cost data (`cost_usd`, `input_tokens`, `output_tokens`, `duration_s`) is
already available from the result capture at that point.
