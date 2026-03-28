# Design: Work Item Duplicate Traces (Defect 18)

## Problem

The traces table on `/item/<slug>` shows the same run appearing twice with slightly
different `created_at` timestamps and the same run_id prefix. The `list_root_traces_by_slug`
query already filters `parent_run_id IS NULL`, so child runs are not the cause.

## Root Cause

The `traces` table has no UNIQUE constraint on `run_id`. If a LangChain callback fires
twice for the same run event (e.g. `on_chain_start` called twice, or a retry), `record_run`
inserts two rows with the same `run_id` but different `created_at` values. Both rows satisfy
`parent_run_id IS NULL AND name LIKE '%slug%'`, so both appear in the item detail page.

## Fix Strategy

Two-layer defence:

1. **Schema**: Add `UNIQUE` constraint on `traces.run_id`. Change `record_run` INSERT to
   `INSERT OR IGNORE` so duplicate calls are silently dropped instead of creating extra rows.
   SQLite does not support `ADD CONSTRAINT` on existing tables, so we use a `CREATE UNIQUE INDEX`
   instead (equivalent and backward-compatible with the existing DB file).

2. **Query**: Update `list_root_traces_by_slug` to use `GROUP BY run_id` with
   `MIN(created_at)` so any pre-existing duplicate rows in deployed databases are
   collapsed to one row per logical run.

## Key Files

| File | Change |
|------|--------|
| `langgraph_pipeline/web/proxy.py` | Add unique index creation in `_CREATE_INDEXES_SQL`; change INSERT to `INSERT OR IGNORE`; update `list_root_traces_by_slug` SQL to `GROUP BY run_id` |
| `tests/langgraph/web/test_proxy.py` | Add tests: duplicate `record_run` inserts only one row; `list_root_traces_by_slug` returns one row per run_id even when DB has pre-existing duplicates |

## Design Decisions

- `INSERT OR IGNORE` (not `INSERT OR REPLACE`) preserves the first-written row and
  discards the duplicate, which is the correct semantic for idempotent callbacks.
- `CREATE UNIQUE INDEX IF NOT EXISTS` on an existing DB file will succeed only if
  there are no duplicate `run_id` values; the `GROUP BY` query fix ensures the UI
  is correct even before existing databases are migrated.
- No migration script is needed — both fixes are backward-compatible with existing
  DB files that have duplicates.
