# Design: Structured Execution Cost Log and Automated Analysis

- **Work item:** docs/feature-backlog/12-structured-execution-cost-log-and-analysis.md
- **Created:** 2026-03-24

## Architecture Overview

The feature adds two things to `scripts/plan-orchestrator.py`:

1. **Per-task cost log**: after each task executes, append a structured JSON record to
   `docs/reports/execution-costs/<item-slug>.json` capturing task id, agent type,
   model, input/output tokens, cost, duration, and tool calls with file paths and
   result sizes.

2. **Analysis backlog template**: `docs/analysis-backlog/cost-analysis.md` — when
   processed by the pipeline, the analysis agent reads all files under
   `docs/reports/execution-costs/`, aggregates by file path and agent type, and
   posts a ranked Slack report.

## Key Files to Create/Modify

| File | Change |
|------|--------|
| `scripts/plan-orchestrator.py` | Add `ToolCallRecord` dataclass, extend `stream_json_output()` to collect tool calls and result sizes, add `write_execution_cost_log()`, call it from `run_claude_task()` |
| `docs/reports/execution-costs/` | Directory created by `write_execution_cost_log()` on first write |
| `docs/analysis-backlog/cost-analysis.md` | New analysis item template |
| `tests/test_execution_cost_log.py` | Unit tests for cost log writer and tool call extraction |

## Data Model

```python
@dataclass
class ToolCallRecord:
    tool: str
    file_path: Optional[str]   # for Read/Edit/Write/Grep/Glob
    command: Optional[str]     # for Bash
    result_bytes: Optional[int]  # bytes returned by tool_result
```

Cost log JSON schema (appended per task, file-level structure):

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

## Implementation Details

### Tool call collection in stream-json mode

`stream_json_output()` currently discards tool_use and tool_result blocks after
printing them. Extend it to:

1. On `tool_use` block: append a `ToolCallRecord` to an in-flight list; store
   `{tool_use_id -> record}` in a pending dict.
2. On `tool_result` block: look up the matching `tool_use_id` in the pending dict;
   set `result_bytes = len(json.dumps(content))` on the record; remove from pending.

The collected list is stored in `result_capture["tool_calls"]` so `run_claude_task()`
can retrieve it after thread join without changing the function signature.

### Tool call collection in non-verbose (json) mode

The `--output-format json` output contains `messages[].content[]` blocks with full
tool_use and tool_result entries. After parsing the JSON output, extract tool calls
using the same pairing logic as above.

### Cost log writer

```python
def write_execution_cost_log(
    item_slug: str,
    item_type: str,
    task_id: str,
    agent_type: str,
    model: str,
    usage: TaskUsage,
    duration_s: float,
    tool_calls: list[ToolCallRecord],
) -> None:
```

- Log directory: `docs/reports/execution-costs/`
- File path: `<log_dir>/<item_slug>.json`
- On first call: create file with outer structure (`item_slug`, `item_type`, `tasks: []`)
- On subsequent calls: load existing file, append new task record, write back

### Integration point

In `run_claude_task()`, after `task_usage = parse_task_usage(result_capture)`:

```python
tool_calls = result_capture.get("tool_calls", [])
```

Return `tool_calls` via `TaskResult` (add optional `tool_calls` field).

In the main execution loop (around line 6342), after recording usage, call
`write_execution_cost_log(...)` when `item_slug` and `item_type` are available
from `meta`.

### Item slug derivation

The item slug is derived from the plan file name stem:
`Path(plan_path).stem` → e.g. `12-structured-execution-cost-log-and-analysis`.
Item type comes from `meta.get("item_type", "feature")`.

## Analysis Backlog Template

`docs/analysis-backlog/cost-analysis.md` instructs the analysis agent to:

1. Read all JSON files under `docs/reports/execution-costs/`
2. Aggregate read volume by file path (sum of `result_bytes` across all `Read` calls)
3. Rank agent types by total token cost
4. Identify tasks that re-read the same files within the same item
5. Post a structured Slack report to `orchestrator-notifications` with findings and
   concrete restructuring recommendations

## Design Decisions

- **Append-per-task rather than batch-at-end**: writing after each task ensures
  partial data is captured even if the pipeline is interrupted mid-item.
- **`result_capture["tool_calls"]` as transport**: avoids changing `stream_json_output`
  signature; the dict is already used to pass the result event back to the caller.
- **Optional result_bytes**: tool_result pairing is best-effort; if the stream
  delivers results out of order or the tool_use_id is missing, `result_bytes` stays
  `None` rather than crashing.
- **Non-verbose mode tool extraction**: duplicates the pairing logic but is
  necessary because the two output formats are structurally different.
