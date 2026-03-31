# Design: 85 Completions Upsert By Slug

Source: tmp/plans/.claimed/85-completions-upsert-by-slug.md
Requirements: docs/plans/2026-03-31-85-completions-upsert-by-slug-requirements.md

## Architecture Overview

The completions table in proxy.py uses a plain INSERT in record_completion and
lacks a UNIQUE constraint on slug. When the supervisor retries a work item
(warn/fail outcome), each attempt inserts a new row, producing duplicates with
separate cost/duration values instead of accumulated totals.

The fix has four parts:

1. **Column migration**: Add an attempts_history TEXT column to the completions
   table for tracking per-attempt details as a JSON array.
2. **Duplicate merge migration**: A Python migration in _init_db that merges
   existing duplicate rows per slug: sums cost_usd and duration_s, takes
   latest-finished_at values for other fields, and builds the attempts_history
   JSON array from all rows.
3. **UNIQUE index**: A UNIQUE index on the slug column, added after the merge.
4. **Upsert logic**: An INSERT ... ON CONFLICT(slug) DO UPDATE in record_completion
   that accumulates cost_usd and duration_s, replaces outcome/finished_at/run_id/
   tokens_per_minute/verification_notes with the latest values, and appends a
   new entry to the attempts_history JSON array.

For the dashboard, once the database enforces one-row-per-slug with accumulated
values, the existing queries return correct totals. The completion_grouping module
is updated to derive attempt_count and retries from the attempts_history JSON
column instead of from multiple rows. The dashboard already has a retry drill-down
UI (toggleRetryRows, tpl-retry-row template, retry count badges) that displays
per-attempt history -- the data just needs to flow from the new column.

## Key Files to Modify

- langgraph_pipeline/web/proxy.py -- migration, _init_db, record_completion, queries
- langgraph_pipeline/web/completion_grouping.py -- use attempts_history for retries
- tests/langgraph/web/test_proxy.py -- tests for upsert, migration, constraint
- tests/langgraph/web/test_completion_grouping.py -- update for new data format

## Design Decisions

### D1: Add attempts_history column to completions table

Addresses: FR2
Satisfies: AC15
Approach: Add an ALTER TABLE migration constant _ALTER_ADD_COMPLETIONS_ATTEMPTS_HISTORY_SQL
that adds an attempts_history TEXT column. Execute it in _init_db with a try/except
for OperationalError (column already exists), following the existing pattern for
_ALTER_ADD_COMPLETIONS_RUN_ID_SQL and similar migrations.
Files: langgraph_pipeline/web/proxy.py

### D2: Merge existing duplicate completion rows via Python migration

Addresses: FR3, P4
Satisfies: AC6, AC19, AC20, AC21, AC22, AC23, AC24, AC26
Approach: Add a _migrate_completion_duplicates(self, conn) method called from _init_db
after the column migration (D1) and before the UNIQUE index (D3). The method:
1. Queries for slugs with COUNT(*) > 1.
2. For each duplicate slug, fetches all rows ordered by finished_at ASC.
3. Computes accumulated cost_usd (sum) and duration_s (sum).
4. Builds an attempts_history JSON array from all rows (each entry: outcome, cost_usd,
   duration_s, finished_at, run_id, tokens_per_minute).
5. Updates the row with the latest finished_at (MAX(id) as tiebreaker) with the
   accumulated values and history.
6. Deletes all other rows for that slug.
7. For non-duplicate rows still missing attempts_history, sets it to a single-entry
   JSON array built from the row's own values.
The migration is idempotent: if no duplicates exist and all rows have
attempts_history, no changes are made.
Files: langgraph_pipeline/web/proxy.py

### D3: Add UNIQUE constraint on slug after migration

Addresses: P2, FR3
Satisfies: AC3, AC4
Approach: Add _CREATE_UNIQUE_INDEX_SLUG_SQL constant with CREATE UNIQUE INDEX IF NOT
EXISTS idx_completions_slug_unique ON completions (slug). Execute in _init_db after
D2 migration completes. A raw INSERT with a duplicate slug will raise
sqlite3.IntegrityError, enforcing the one-row-per-slug invariant at the schema level.
Files: langgraph_pipeline/web/proxy.py

### D4: Upsert in record_completion with field accumulation and history append

Addresses: P1, FR1, FR2
Satisfies: AC1, AC2, AC7, AC8, AC9, AC10, AC11, AC12, AC13, AC14, AC16, AC17, AC18, AC25
Approach: Replace the plain INSERT in record_completion with INSERT INTO completions
(..., attempts_history) VALUES (..., ?) ON CONFLICT(slug) DO UPDATE SET
item_type=excluded.item_type, outcome=excluded.outcome,
cost_usd=completions.cost_usd + excluded.cost_usd,
duration_s=completions.duration_s + excluded.duration_s,
finished_at=excluded.finished_at, run_id=excluded.run_id,
tokens_per_minute=excluded.tokens_per_minute,
verification_notes=excluded.verification_notes,
attempts_history=json_insert(completions.attempts_history, '$[#]', json(?)).

On first insert, attempts_history is initialized to a single-entry JSON array
containing the attempt's fields. On conflict, the new attempt entry is appended
via json_insert to the existing array.
Files: langgraph_pipeline/web/proxy.py

### D5: Dashboard queries and grouping updated for attempts_history

Addresses: P3, UC1
Satisfies: AC5, AC27, AC28, AC29
Approach: Once the DB has one row per slug with accumulated cost/duration (D2+D4),
existing queries return correct summary data. Update the SELECT statements in
list_completions, list_completions_grouped, and list_completions_by_slug to include
attempts_history. Update completion_grouping.py to parse attempts_history from each
row and derive attempt_count (length of array) and retries (all but last entry),
instead of building retries from multiple database rows. The dashboard already has
retry drill-down UI (toggleRetryRows, tpl-retry-row template, retry badges) that
renders per-attempt history from the retries field -- no template changes needed.
Files: langgraph_pipeline/web/proxy.py, langgraph_pipeline/web/completion_grouping.py

## Design -> AC Traceability

| AC | Design Decision(s) | Approach |
|---|---|---|
| AC1 | D4 | ON CONFLICT upsert prevents duplicate rows on retry |
| AC2 | D4 | Upsert detects existing slug and updates instead of inserting |
| AC3 | D3 | UNIQUE index on slug column enforces constraint |
| AC4 | D3 | Raw INSERT with duplicate slug raises IntegrityError |
| AC5 | D5 | One row per slug in DB; grouping reads single row |
| AC6 | D2 | Migration merges duplicates; one row per slug after completion |
| AC7 | D4 | INSERT path creates new row on first call for a slug |
| AC8 | D4 | cost_usd = completions.cost_usd + excluded.cost_usd |
| AC9 | D4 | duration_s = completions.duration_s + excluded.duration_s |
| AC10 | D4 | outcome = excluded.outcome (latest attempt) |
| AC11 | D4 | finished_at = excluded.finished_at (latest attempt) |
| AC12 | D4 | run_id = excluded.run_id (latest attempt) |
| AC13 | D4 | tokens_per_minute = excluded.tokens_per_minute (latest attempt) |
| AC14 | D4 | verification_notes = excluded.verification_notes (latest attempt) |
| AC15 | D1 | ALTER TABLE adds attempts_history TEXT column |
| AC16 | D4 | First insert initializes attempts_history with single-entry array |
| AC17 | D4 | ON CONFLICT appends new entry to existing array via json_insert |
| AC18 | D4 | Each history entry includes outcome, cost_usd, duration_s, finished_at, run_id, tokens_per_minute |
| AC19 | D2 | Migration sums cost_usd across all rows for merged slug |
| AC20 | D2 | Migration sums duration_s across all rows for merged slug |
| AC21 | D2 | Merged row outcome/finished_at/run_id/tpm/notes from latest row |
| AC22 | D2 | Migration builds attempts_history from all rows ordered by finished_at |
| AC23 | D2 | Extra rows deleted; only merged row remains per slug |
| AC24 | D2 | Migration is no-op for slugs with only one row |
| AC25 | D4 | record_completion uses INSERT...ON CONFLICT(slug) pattern |
| AC26 | D2 | Migration runs in _init_db in proxy.py |
| AC27 | D5 | Accumulated cost/duration stored in DB; grouping reads them |
| AC28 | D5 | attempts_history passed through to dashboard via retries field |
| AC29 | D5 | Each attempt entry in history has all required detail fields |
