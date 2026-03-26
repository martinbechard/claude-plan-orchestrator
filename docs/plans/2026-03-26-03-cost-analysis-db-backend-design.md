# Design: Cost Analysis DB Backend

Feature 03 | 2026-03-26

## Status

Most of the implementation was completed by a prior agent attempt. All four components
are in place:

- `cost_tasks` table — created by `_CREATE_COST_TASKS_SQL` in `proxy.py`, called from
  `_init_db()` at startup
- `TracingProxy.record_cost_task()` — persists rows to the DB
- `POST /api/cost` endpoint — `routes/cost.py`, registered in `server.py`
- `write_execution_cost_log()` in `plan-orchestrator.py` — calls `_post_cost_to_db()`
  when `LANGCHAIN_ENDPOINT` starts with `http://localhost`, falls back to JSON files
- `CostLogReader.load_all()` — queries `cost_tasks` first, falls back to JSON files

## Remaining Issues

### Issue 1 — 4 failing unit tests (test_execution_cost_log.py)

Tests monkeypatch `COST_LOG_DIR` but not `LANGCHAIN_ENDPOINT`. When the pipeline web
server is running in the environment, `write_execution_cost_log` POSTs successfully and
returns early without writing the JSON file, causing `FileNotFoundError` in the tests.

Fix: each test that exercises the JSON fallback path must also call
`monkeypatch.delenv("LANGCHAIN_ENDPOINT", raising=False)`.

### Issue 2 — item_type always "feature"

`plan-orchestrator.py` line 6556:

    item_type=meta.get("item_type", "feature")

Plan YAML files do not include `item_type` in meta, so this always returns `"feature"`
even for defect plans. The correct value is derivable from the `source_item` path stored
in meta: if `"defect"` appears in the path, the item is a defect.

Fix: replace the static default with a one-liner that inspects `meta.get("source_item", "")`.

## Architecture

No new files, no schema changes. Both fixes are small targeted edits.

```
plan-orchestrator.py (worker)
  write_execution_cost_log()
    ├── if LANGCHAIN_ENDPOINT starts with http://localhost:
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

## Files to Modify

| File | Change |
|------|--------|
| `tests/test_execution_cost_log.py` | Add `monkeypatch.delenv("LANGCHAIN_ENDPOINT", raising=False)` to 4 failing tests |
| `scripts/plan-orchestrator.py` | Derive `item_type` from `source_item` path instead of static default |

## Design Decisions

**Tests drive the JSON path explicitly** — clearing the env var is simpler than mocking
the HTTP call and tests the actual fallback condition used in production.

**item_type derivation** — a simple `"defect" in source_item` check is sufficient since
backlog file paths use `defect-backlog/` or `feature-backlog/` directories consistently.
No new constant or helper function needed beyond a conditional expression.
