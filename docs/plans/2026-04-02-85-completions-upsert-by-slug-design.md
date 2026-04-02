# Design: 85 Completions Upsert By Slug

Source: tmp/plans/.claimed/85-completions-upsert-by-slug.md
Requirements: docs/plans/2026-04-02-85-completions-upsert-by-slug-requirements.md

## Architecture Overview

The completions table in proxy.py previously used a plain INSERT in record_completion
and lacked a UNIQUE constraint on slug. When the supervisor retried a work item
(warn/fail outcome), each attempt inserted a new row, producing duplicates with
separate cost/duration values instead of accumulated totals.

The fix has five parts:

1. **Column migration** (DONE): Add an attempts_history TEXT column to the completions
   table for tracking per-attempt details as a JSON array.
2. **Duplicate merge migration** (DONE): A Python migration in _init_db that merges
   existing duplicate rows per slug: sums cost_usd and duration_s, takes
   latest-finished_at values for other fields, and builds the attempts_history
   JSON array from all rows.
3. **UNIQUE index** (DONE): A UNIQUE index on the slug column, added after the merge.
4. **Upsert logic** (DONE): An INSERT ... ON CONFLICT(slug) DO UPDATE in record_completion
   that accumulates cost_usd and duration_s, replaces outcome/finished_at/run_id/
   tokens_per_minute/verification_notes with the latest values, and appends a
   new entry to the attempts_history JSON array.
5. **Query and grouping adaptation** (REMAINING): Update SELECT queries and
   completion_grouping.py to include and use attempts_history, and remove the
   GROUPED_QUERY_MULTIPLIER over-fetch since the DB now has one row per slug.

## Key Files to Modify

- langgraph_pipeline/web/proxy.py -- update SELECT queries to include attempts_history
- langgraph_pipeline/web/completion_grouping.py -- derive retries from attempts_history
- tests/langgraph/web/test_proxy.py -- verify queries return attempts_history
- tests/langgraph/web/test_completion_grouping.py -- update for new data format

## Design Decisions

### D1: Add attempts_history column to completions table

Addresses: FR9
Satisfies: AC15
Approach: Add an ALTER TABLE migration constant _ALTER_ADD_COMPLETIONS_ATTEMPTS_HISTORY_SQL
that adds an attempts_history TEXT column. Execute it in _init_db with a try/except
for OperationalError (column already exists), following the existing pattern for
_ALTER_ADD_COMPLETIONS_RUN_ID_SQL and similar migrations.
Files: langgraph_pipeline/web/proxy.py
Status: IMPLEMENTED

### D2: Merge existing duplicate completion rows via Python migration

Addresses: FR10
Satisfies: AC21, AC22, AC23, AC24, AC25, AC26, AC27
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
Status: IMPLEMENTED

### D3: Add UNIQUE constraint on slug after migration

Addresses: P2, FR11
Satisfies: AC4, AC5, AC28, AC29
Approach: Add _CREATE_UNIQUE_INDEX_SLUG_SQL constant with CREATE UNIQUE INDEX IF NOT
EXISTS idx_completions_slug_unique ON completions (slug). Execute in _init_db after
D2 migration completes. A raw INSERT with a duplicate slug will raise
sqlite3.IntegrityError, enforcing the one-row-per-slug invariant at the schema level.
Files: langgraph_pipeline/web/proxy.py
Status: IMPLEMENTED

### D4: Upsert in record_completion with field accumulation and history append

Addresses: P1, FR1, FR2, FR3, FR4, FR5, FR6, FR7, FR8, FR9
Satisfies: AC1, AC2, AC3, AC6, AC7, AC8, AC9, AC10, AC11, AC12, AC13, AC14, AC16, AC17
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
Status: IMPLEMENTED

### D5: Update queries and grouping to use attempts_history

Addresses: UC1
Satisfies: AC18, AC19, AC20
Approach: Update the SELECT statements in list_completions, list_completions_grouped,
and list_completions_by_slug to include attempts_history. Update completion_grouping.py
to parse attempts_history JSON from each row and derive attempt_count (len of array)
and retries (all entries except the last) instead of building retries from multiple
database rows. Since the DB now has one row per slug, list_completions_grouped no
longer needs to over-fetch by GROUPED_QUERY_MULTIPLIER -- simplify the query to use
the limit directly. The dashboard already has retry drill-down UI (toggleRetryRows,
tpl-retry-row template, retry badges) that renders per-attempt history from the
retries field -- no template changes needed, the data just needs to flow from the
new column.
Files: langgraph_pipeline/web/proxy.py, langgraph_pipeline/web/completion_grouping.py
Status: REMAINING

## Design -> AC Traceability

| AC | Design Decision(s) | Approach |
|---|---|---|
| AC1 | D4 | ON CONFLICT upsert prevents duplicate rows on retry |
| AC2 | D4 | Dashboard sees one row per slug because DB enforces it |
| AC3 | D4 | record_completion uses ON CONFLICT which checks for existing slug |
| AC4 | D3 | UNIQUE index on slug column enforces constraint |
| AC5 | D3 | Raw INSERT with duplicate slug raises IntegrityError |
| AC6 | D4 | INSERT...ON CONFLICT(slug) is the upsert pattern |
| AC7 | D4 | INSERT path creates new row; ON CONFLICT updates existing |
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
| AC18 | D5 | One row per slug in DB; grouping reads single row with history |
| AC19 | D5 | Accumulated cost_usd/duration_s stored in DB, passed through queries |
| AC20 | D5 | attempts_history parsed in grouping, retries exposed to dashboard |
| AC21 | D2 | Migration merges duplicates; one row per slug after completion |
| AC22 | D2 | Migration sums cost_usd across all rows for merged slug |
| AC23 | D2 | Migration sums duration_s across all rows for merged slug |
| AC24 | D2 | Merged row outcome/finished_at/run_id/tpm/notes from latest row |
| AC25 | D2 | Migration builds attempts_history from all rows ordered by finished_at |
| AC26 | D2 | Extra rows deleted; only merged row remains per slug |
| AC27 | D2 | Migration runs in _init_db in proxy.py |
| AC28 | D3 | UNIQUE constraint added after migration in _init_db |
| AC29 | D3 | Duplicate INSERT raises constraint violation |
