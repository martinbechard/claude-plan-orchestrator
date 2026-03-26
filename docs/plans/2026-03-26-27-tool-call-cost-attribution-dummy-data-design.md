# Tool Call Cost Attribution — Replace Dummy Data Design

Work item: .claude/plans/.claimed/27-tool-call-cost-attribution-dummy-data.md

## Problem

The cost analysis page's "Tool Call Cost Attribution" table shows no data (or dummy data)
because:

1. The `cost_tasks` table contains 153 stale test rows for `item_slug = "12-test-item"`,
   all with empty `tool_calls_json = []` — seeded during initial feature development.
2. The langgraph executor nodes (`task_runner.py`, `validator.py`) never POST to
   `/api/cost`, so real task executions produce no `cost_tasks` rows.
3. `ToolCallRecord` in `claude_cli.py` does not capture `result_bytes` from tool results,
   so even if we wire the POST, the attribution computation has no data to proportion over.

## Architecture

The attribution pipeline (post-hoc, Option 2 from feature 11 design) is already built:

```
Claude CLI output → stream_json_output → tool_calls: list[ToolCallRecord]
                                         ↓ (missing wiring)
                              POST /api/cost (cost_tasks row)
                                         ↓
               TracingProxy.get_tool_call_attribution() → analysis page
```

The fix closes the missing wiring and adds `result_bytes` capture.

## Changes

### 1. `langgraph_pipeline/shared/claude_cli.py`

Add `result_bytes: NotRequired[Optional[int]]` to `ToolCallRecord` TypedDict.

In `stream_json_output`, when processing a `user` event with a `tool_result` block,
compute the byte size of the result content (`len(json.dumps(content))`) and store it
in the matching pending record alongside `duration_s`.

### 2. `langgraph_pipeline/executor/nodes/task_runner.py`

Add `_post_cost_to_api()` helper:

- Reads `LANGCHAIN_ENDPOINT` from env; skips if not set to a localhost URL.
- Extracts item_slug and item_type from `plan_data.meta.source_item` (stem of the path).
- Converts `list[ToolCallRecord]` → list of `{tool, file_path?, command?, result_bytes?}`
  dicts, using the same field-mapping logic as `proxy.get_tool_call_attribution()`.
- POSTs JSON to `{endpoint}/api/cost` (fire-and-forget, non-fatal on error).

Call `_post_cost_to_api()` after `_run_claude()` returns in `execute_task()`, passing
task_id, cost_usd, input_tokens, output_tokens, duration_s, and tool_calls.

### 3. `langgraph_pipeline/executor/nodes/validator.py`

The validator's local `_run_claude()` does not pass a `tool_calls` list to
`stream_json_output`. Update it to match task_runner pattern: accept and populate
`tool_calls: list[ToolCallRecord]`.

Add the same `_post_cost_to_api()` call after execution (agent_type = "validator").

### 4. Dummy data cleanup

Run `DELETE FROM cost_tasks WHERE item_slug = '12-test-item'` on the traces DB
(`~/.claude/orchestrator-traces.db`). This removes the 153 stale test rows so the
page renders cleanly from real data.

## Key Files

### Modify
- `langgraph_pipeline/shared/claude_cli.py` — add result_bytes to ToolCallRecord + capture
- `langgraph_pipeline/executor/nodes/task_runner.py` — add _post_cost_to_api + wire call
- `langgraph_pipeline/executor/nodes/validator.py` — add tool_calls capture + wire cost POST

### No changes needed
- `langgraph_pipeline/web/routes/cost.py` — already accepts tool_calls_json correctly
- `langgraph_pipeline/web/proxy.py` — get_tool_call_attribution() already correct
- `langgraph_pipeline/web/templates/analysis.html` — already has attribution section

## Design Decisions

- `result_bytes` is computed as `len(json.dumps(content))` — mirrors what
  `plan-orchestrator.py` does in `_extract_tool_calls_from_json_output()`.
- POST is fire-and-forget; a logging warning on failure is sufficient — cost recording
  is observability, not correctness.
- `item_type` is derived from `source_item` path: contains "defect" → "defect", else
  "feature". Mirrors the existing convention.
- Only tool_use records (not text blocks) are included in the cost POST.
- The dummy data DELETE is a one-time cleanup; no ongoing guard is needed.
