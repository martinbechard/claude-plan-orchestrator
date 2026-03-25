# Structured execution cost log and automated token/time analysis

## Status: Open

## Priority: Medium

## Summary

The pipeline currently captures token counts and tool calls per task but never
writes them to disk in a structured form. There is no way to answer questions like
"which files are we loading repeatedly across tasks?" or "which agent types consume
the most tokens?" without manually inspecting LangSmith traces one by one.

This feature adds two things:

1. **Structured cost log**: after each task execution, append a JSON record to
   `docs/reports/execution-costs/<item-slug>.json` capturing task id, agent type,
   model, input/output tokens, cost, duration, and the full tool call list with file
   paths. Also capture tool result sizes (bytes returned per Read/Bash call) via the
   `tool_use_id` pairing already used by feature 03, to enable token attribution at
   the file level.

2. **Automated analysis item**: a reusable template placed in `docs/analysis-backlog/`
   that triggers the pipeline's analysis workflow to read the cost logs and post a
   structured Slack report identifying: files with the highest total read volume across
   all invocations, task types with the highest token cost, tasks that re-read the same
   files within the same item, and concrete restructuring recommendations (e.g. "tasks
   X and Y both load files A, B, C — consider merging into one invocation").

## 5 Whys Analysis

1. **Why can't we tell what's consuming most of our tokens?** Token counts are
   accumulated as session totals in PipelineState and per-task in result_capture, but
   never written to disk broken down by file or agent type.
2. **Why does that matter?** Without attribution, we cannot tell whether cost is
   dominated by repeated file reads, by large system prompts, by verbose tool outputs,
   or by a specific agent type — so we cannot prioritise optimisation efforts.
3. **Why not just use LangSmith?** LangSmith traces (features 03 and 09) show tool
   call timelines but cannot attribute input token cost to specific files without
   capturing tool result sizes. Analysis also requires manual UI navigation rather
   than automated reporting.
4. **Why are repeated file reads a likely source of waste?** Each Claude Code
   invocation starts with a fresh context. If tasks A and B both need to understand
   the same module, each will independently issue Read calls for the same files,
   paying the token cost twice. Identifying these patterns is the first step to
   restructuring or caching.
5. **Why automate the analysis as a pipeline item?** The analysis backlog workflow
   (feature 17, completed) already supports read-only analysis tasks that produce
   Slack reports. Using it here means the analysis runs automatically and delivers
   actionable findings without manual script execution.

**Root Need:** Persist structured per-task execution data (tokens, costs, tool calls
with file paths and result sizes) to disk so that automated analysis can surface
token and time waste patterns and recommend concrete restructuring actions.

## Implementation Notes

**Cost log format** (`docs/reports/execution-costs/<item-slug>.json`):
```json
{
  "item_slug": "12-structured-execution-cost-log",
  "item_type": "feature",
  "tasks": [
    {
      "task_id": "1.1",
      "agent_type": "coder",
      "model": "claude-sonnet-4-6",
      "input_tokens": 42000,
      "output_tokens": 1800,
      "cost_usd": 0.042,
      "duration_s": 87.3,
      "tool_calls": [
        {"tool": "Read", "file_path": "src/foo.py", "result_bytes": 4200},
        {"tool": "Bash", "command": "pnpm run build", "result_bytes": 380}
      ]
    }
  ]
}
```

**Capturing result sizes**: use the `tool_use_id` pairing introduced by feature 03.
When a `tool_result` block arrives in the stream, record `len(content)` alongside the
matching `tool_use_id`. Add `result_bytes: Optional[int]` to `ToolCallRecord`.

**Where to write the log**: in `execute_task` (task_runner.py) after `emit_tool_call_traces`,
append the task record to the item's cost log file. Create the file on first task.

**Analysis item template**: `docs/analysis-backlog/cost-analysis.md` — when processed,
the analysis agent reads all files under `docs/reports/execution-costs/`, aggregates
by file path and agent type, and posts a ranked report to `orchestrator-notifications`.

**Relationship to other features**: feature 03 (tool_use_id duration pairing) and
feature 09 (LangSmith root trace) are complementary — the cost log provides local,
queryable, file-level data that LangSmith traces cannot supply.

## Source

Proposed on 2026-03-24 as Option C from a three-option analysis of token/time cost
observability approaches.
