# Design: Fix Duplicate Trace Rows (Start and End Events)

## Problem

The trace detail page shows each pipeline step twice because `TracingProxy.record_run()`
uses `INSERT OR IGNORE`, which silently drops the completion event instead of updating
the existing start-event row. Worse, if the database already contains duplicate run_ids
(from before the unique index was added), `CREATE UNIQUE INDEX` throws `IntegrityError`
and is caught and swallowed, so no unique constraint is ever enforced. Both `INSERT OR IGNORE`
and the `ON CONFLICT` clause require an active UNIQUE constraint to fire; without it, every
call does a plain INSERT, producing two rows per node.

## Fix Strategy

### 1. Deduplicate existing rows before creating the unique index

`_init_db` must clean up pre-existing duplicates before attempting `CREATE UNIQUE INDEX`.
For each `run_id` that appears more than once, keep the row with the latest `created_at`
(which is the completion event, likely to have `end_time` and `outputs_json` populated),
then delete the others.

```sql
DELETE FROM traces
WHERE id NOT IN (
    SELECT MAX(id) FROM traces GROUP BY run_id
)
AND run_id IN (
    SELECT run_id FROM traces GROUP BY run_id HAVING COUNT(*) > 1
);
```

After deduplication, `CREATE UNIQUE INDEX IF NOT EXISTS idx_traces_run_id_unique` will
succeed for all databases.

### 2. Switch from INSERT OR IGNORE to upsert

Replace the plain `INSERT OR IGNORE` in `record_run()` with an upsert that updates only
the fields that arrive in the completion event:

```sql
INSERT INTO traces (run_id, parent_run_id, name, start_time, end_time,
                    inputs_json, outputs_json, metadata_json, error, created_at)
VALUES (:run_id, :parent_run_id, :name, :start_time, :end_time,
        :inputs_json, :outputs_json, :metadata_json, :error, :created_at)
ON CONFLICT(run_id) DO UPDATE SET
    end_time     = excluded.end_time,
    outputs_json = excluded.outputs_json,
    error        = excluded.error
```

Fields intentionally not updated on conflict: `parent_run_id`, `name`, `inputs_json`,
`metadata_json`, `start_time`, `created_at` — these do not change between the start and
completion events.

## Key Files to Modify

- `langgraph_pipeline/web/proxy.py`
  - `_init_db()`: add deduplication step before `CREATE UNIQUE INDEX`
  - `record_run()`: replace `INSERT OR IGNORE` with upsert
- `tests/langgraph/web/test_proxy.py`
  - Add tests for upsert behavior (start event + completion event produces one row)
  - Add test that deduplication runs on init with a pre-seeded DB containing duplicates

## Design Decisions

- Keep the deduplication in `_init_db` so it runs once on server startup for any
  existing database, not on every insert.
- The `ON CONFLICT` clause uses the column-level conflict target `(run_id)`, which
  requires the unique index to exist — guaranteed after the deduplication step.
- `IntegrityError` catch around `CREATE UNIQUE INDEX` is removed once deduplication
  always runs first.
