# Design: Cost Analysis DB Backend

Feature 03 | 2026-03-26

## Overview

The `/analysis` page is always empty because the LangGraph pipeline never writes cost data.
`write_execution_cost_log()` exists only in `scripts/plan-orchestrator.py` and writes JSON
files. This feature ports cost logging to the SQLite DB already used by the TracingProxy,
adds an HTTP endpoint to accept per-task cost records, updates the worker to POST to that
endpoint, and updates `CostLogReader` to query the DB.

## Architecture

```
plan-orchestrator.py (worker)
  write_execution_cost_log()
    ├── if LANGCHAIN_ENDPOINT points at localhost:
    │     POST http://localhost:<port>/api/cost  ──► FastAPI /api/cost
    │                                                   │
    │                                          cost.py router
    │                                                   │
    │                                          INSERT INTO cost_tasks
    │                                          (~/.claude/orchestrator-traces.db)
    └── else: write JSON file (unchanged fallback)

GET /analysis
  CostLogReader.load_all()
    ├── try: query cost_tasks DB  ──► aggregate into CostData
    └── fallback: read JSON files (when DB unavailable)
```

## Key Files

| File | Action |
|------|--------|
| `langgraph_pipeline/web/proxy.py` | Add `_CREATE_COST_TASKS_SQL` and create the table in `_init_db()` |
| `langgraph_pipeline/web/routes/cost.py` | Create — `POST /api/cost` router |
| `langgraph_pipeline/web/server.py` | Register `cost_router` in `create_app()` |
| `langgraph_pipeline/web/cost_log_reader.py` | Add `_load_from_db()` path; fall back to JSON files |
| `scripts/plan-orchestrator.py` | Update `write_execution_cost_log()` to POST when LANGCHAIN_ENDPOINT is localhost |
| `tests/langgraph/web/test_cost_endpoint.py` | Create — unit tests for POST /api/cost |
| `tests/langgraph/web/test_cost_log_reader.py` | Update/create — tests for DB-backed load_all() |

## Design Decisions

**DB reuse** — The `cost_tasks` table is added to the existing
`~/.claude/orchestrator-traces.db` managed by `TracingProxy`. This avoids a second DB file
and leverages the already-established connection pattern in `proxy.py`.

**New route file** — `POST /api/cost` goes in `langgraph_pipeline/web/routes/cost.py`
to mirror the existing router pattern (`analysis.py`, `dashboard.py`, `proxy.py`).

**202 response** — The endpoint returns 202 so the caller (plan-orchestrator.py) is never
blocked waiting for a DB commit ACK. The response body is `{"ok": true}`.

**Caller detection** — `write_execution_cost_log()` in plan-orchestrator.py reads
`LANGCHAIN_ENDPOINT` (already set by the supervisor before launching the worker process).
When it starts with `http://localhost`, it POSTs to `/api/cost`; otherwise it writes a JSON
file. Both paths remain active so the JSON fallback works when the web server is not running.

**CostLogReader fallback** — `load_all()` tries the DB first (using `DB_DEFAULT_PATH` from
`proxy.py`). If the DB file does not exist or the table is absent, it falls back to the
existing JSON file glob. This keeps backward compatibility when the web server has never run.

**No tool_calls in DB** — `tool_calls` is stored as a JSON text column (`tool_calls_json`)
matching the design schema. `CostLogReader` deserialises it the same way it currently reads
the JSON field from files.
