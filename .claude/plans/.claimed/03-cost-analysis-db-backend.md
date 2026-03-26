# Cost Analysis DB Backend

## Status: Open

## RETURNED FROM COMPLETED — Previous Implementation Was Incomplete

This item was previously marked as completed but the implementation is half-baked:
- The cost_tasks DB table exists but only contains fake test data (item
  "12-test-item" with dummy coder/validator tasks).
- The POST /api/cost endpoint may exist but no real pipeline worker is calling it.
- The /analysis page shows test data (foo.py file, test item) not real pipeline data.
- The "Tool-Call Duration Histogram" section says "not yet available".
- CostLogReader reads from DB but the DB is empty of real data.

The previous agent used Sonnet (not Opus) and appears to have inserted test
fixtures then declared success without verifying real end-to-end data flow.

This item needs to be re-done properly with real integration testing.

## Problem

The `/analysis` page is always empty. `write_execution_cost_log()` exists only in
`scripts/plan-orchestrator.py` and writes JSON files to `docs/reports/execution-costs/`.
The new LangGraph pipeline (`langgraph_pipeline/`) never calls it, so no data is ever
written and the cost analysis page has nothing to display.

## Goal

Port cost logging to the new pipeline by:
1. Adding a `cost_tasks` table to the existing SQLite DB (`~/.claude/orchestrator-traces.db`)
2. Adding a `POST /api/cost` endpoint to the web server that accepts a per-task cost record
   and inserts it into the DB
3. Updating `plan-orchestrator.py` (the worker) to POST to `http://localhost:<port>/api/cost`
   instead of writing JSON files, when the web server is running
4. Updating `CostLogReader` in `langgraph_pipeline/web/cost_log_reader.py` to query the DB
   instead of reading JSON files

## DB Schema

```sql
CREATE TABLE IF NOT EXISTS cost_tasks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    item_slug    TEXT NOT NULL,
    item_type    TEXT NOT NULL,
    task_id      TEXT NOT NULL,
    agent_type   TEXT NOT NULL,
    model        TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd     REAL NOT NULL DEFAULT 0.0,
    duration_s   REAL NOT NULL DEFAULT 0.0,
    tool_calls_json TEXT,
    recorded_at  TEXT NOT NULL
);
```

## POST /api/cost Payload

```json
{
  "item_slug": "01-some-feature",
  "item_type": "feature",
  "task_id": "1.1",
  "agent_type": "coder",
  "model": "claude-sonnet-4-6",
  "input_tokens": 12000,
  "output_tokens": 3400,
  "cost_usd": 0.0124,
  "duration_s": 47.2,
  "tool_calls": [
    {"tool": "Read", "file_path": "some/file.py", "result_bytes": 4200},
    {"tool": "Bash", "command": "pytest tests/", "result_bytes": 800}
  ]
}
```

The endpoint returns `{"ok": true}` on success and 202 so the caller is never blocked.
The port is read from `LANGCHAIN_ENDPOINT` env var (already set by `configure_tracing()`).

## CostLogReader Changes

Replace the JSON file glob with a DB query:
- `load_all()` queries `cost_tasks` grouped by `item_slug`
- Falls back gracefully to empty `CostData` when DB is unavailable

## Acceptance Criteria

- `POST /api/cost` stores a row in `cost_tasks`
- `plan-orchestrator.py` calls `POST /api/cost` instead of writing JSON when
  `LANGCHAIN_ENDPOINT` is set to localhost
- `/analysis` displays real data after at least one worker completes
- Existing JSON file fallback still works when web server is not running
- All existing tests pass

## LangSmith Trace: ef23382d-7200-4c7e-bb47-10a841fa5876
