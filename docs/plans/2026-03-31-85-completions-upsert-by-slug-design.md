# Design: 85 Completions Upsert By Slug

Source: tmp/plans/.claimed/85-completions-upsert-by-slug.md
Requirements: docs/plans/2026-03-31-85-completions-upsert-by-slug-requirements.md

## Architecture Overview

The completions table in proxy.py uses a plain INSERT in record_completion and
lacks a UNIQUE constraint on slug. When the supervisor retries a work item
(warn/fail outcome), each attempt inserts a new row, producing duplicates with
separate cost/duration values instead of accumulated totals.

The fix has four parts:

1. Add an attempts_history TEXT column to the completions table for tracking
   per-attempt details as a JSON array.
2. A Python migration in _init_db that merges existing duplicate rows per slug:
   sums cost_usd and duration_s, takes latest-finished_at values for other fields,
   and builds the attempts_history JSON array from all rows.
3. A UNIQUE index on the slug column, added after the migration.
4. An INSERT ... ON CONFLICT(slug) DO UPDATE in record_completion that accumulates
   cost_usd and duration_s (adding to existing totals), replaces outcome/finished_at/
   run_id/tokens_per_minute/verification_notes with the latest values, and appends
   a new entry to the attempts_history JSON array.

For the dashboard, once the database enforces one-row-per-slug with accumulated
values, the existing queries naturally return correct totals. The
completion_grouping module is updated to derive attempt_count and retries from
the attempts_history JSON column instead of from multiple rows. A UI drill-down
for attempt history (UC1/AC36) requires a frontend change to expose the
attempts_history data.

## Key Files to Modify

- langgraph_pipeline/web/proxy.py -- migration, _init_db, record_completion, query updates
- langgraph_pipeline/web/completion_grouping.py -- use attempts_history for retries
- tests/langgraph/web/test_proxy.py -- new tests for upsert, migration, and constraint
- Dashboard template -- attempt history drill-down (UC1)

## Design Decisions

### D1: Add attempts_history column to completions table

Addresses: FR2
Satisfies: AC17
Approach: Add an ALTER TABLE migration constant _ALTER_ADD_COMPLETIONS_ATTEMPTS_HISTORY_SQL
that adds an attempts_history TEXT column to the completions table. Execute it in _init_db
with a try/except for OperationalError (column already exists), following the existing
pattern for _ALTER_ADD_COMPLETIONS_RUN_ID_SQL and similar migrations.
Files: langgraph_pipeline/web/proxy.py

### D2: Merge existing duplicate completion rows via Python migration

Addresses: FR3
Satisfies: AC21, AC22, AC23, AC24, AC25, AC26, AC27, AC28, AC29, AC30
Approach: Add a _migrate_completion_duplicates(conn) method called from _init_db after
the column migration (D1) and before the UNIQUE index (D3). The method:
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

Addresses: FR4, P2
Satisfies: AC3, AC4, AC31, AC32
Approach: Add _CREATE_UNIQUE_INDEX_SLUG_SQL constant with CREATE UNIQUE INDEX IF NOT
EXISTS idx_completions_slug_unique ON completions (slug). Execute it in _init_db after
D2 migration completes. A raw INSERT with a duplicate slug will raise
sqlite3.IntegrityError, enforcing the one-row-per-slug invariant at the schema level.
Files: langgraph_pipeline/web/proxy.py

### D4: Upsert in record_completion with field accumulation and history append

Addresses: FR1, FR2, P1
Satisfies: AC1, AC2, AC7, AC8, AC9, AC10, AC11, AC12, AC13, AC14, AC15, AC16, AC18, AC19, AC20
Approach: Replace the plain INSERT in record_completion with INSERT ... ON CONFLICT(slug)
DO UPDATE SET that:
- Accumulates: cost_usd = completions.cost_usd + excluded.cost_usd,
  duration_s = completions.duration_s + excluded.duration_s
- Replaces: item_type, outcome, finished_at, run_id, tokens_per_minute,
  verification_notes from excluded (latest attempt)
- Appends: uses json_insert(completions.attempts_history, '$[#]', json(?)) to append
  a new entry to the existing attempts_history array

On first insert, attempts_history is initialized to a single-entry JSON array.
On conflict, the new attempt is appended to the existing array.
Files: langgraph_pipeline/web/proxy.py

### D5: Dashboard queries and grouping updated for attempts_history

Addresses: P3, UC1
Satisfies: AC5, AC6, AC33, AC34, AC35
Approach: Once the DB has one row per slug with accumulated cost/duration (D2+D4),
existing queries naturally return correct summary data. Update the SELECT statements in
list_completions, list_completions_grouped, and list_completions_by_slug to include the
attempts_history column. Update completion_grouping.py to parse attempts_history from
the row and derive attempt_count (length of array) and retries (all but last entry)
from it, instead of relying on multiple database rows. No template changes needed for
P3 -- the dashboard already renders one row per grouped slug.
Files: langgraph_pipeline/web/proxy.py, langgraph_pipeline/web/completion_grouping.py

### D6: Dashboard attempt history drill-down UI

Addresses: UC1
Satisfies: AC36
Approach: Add an expandable detail section to each completion row in the dashboard that
shows the per-attempt history. Each entry displays outcome, cost_usd, duration_s,
finished_at, run_id, and tokens_per_minute. The data comes from the attempts_history
field already included in the grouped completion response (D5). This requires a
Phase 0 design competition to determine the best UI pattern for the drill-down.
Files: Dashboard templates (determined by Phase 0 winner)

## Design -> AC Traceability

| AC | Design Decision(s) | Approach |
|---|---|---|
| AC1 | D4 | ON CONFLICT upsert prevents duplicate rows on retry |
| AC2 | D4 | Upsert detects existing slug and updates instead of inserting |
| AC3 | D3 | UNIQUE index on slug column enforces constraint |
| AC4 | D3 | Raw INSERT with duplicate slug raises IntegrityError |
| AC5 | D5 | One row per slug in DB; dashboard queries return one entry |
| AC6 | D5 | Accumulated cost/duration stored in DB; dashboard reads them |
| AC7 | D4 | INSERT path creates new row on first call for a slug |
| AC8 | D4 | ON CONFLICT path updates existing row on subsequent calls |
| AC9 | D4 | cost_usd = completions.cost_usd + excluded.cost_usd |
| AC10 | D4 | duration_s = completions.duration_s + excluded.duration_s |
| AC11 | D4 | outcome = excluded.outcome (latest attempt) |
| AC12 | D4 | finished_at = excluded.finished_at (latest attempt) |
| AC13 | D4 | run_id = excluded.run_id (latest attempt) |
| AC14 | D4 | tokens_per_minute = excluded.tokens_per_minute (latest attempt) |
| AC15 | D4 | verification_notes = excluded.verification_notes (latest attempt) |
| AC16 | D4 | On conflict: accumulates cost/duration, appends history, updates fields |
| AC17 | D1 | ALTER TABLE adds attempts_history TEXT column |
| AC18 | D4 | First insert initializes attempts_history with single-entry array |
| AC19 | D4 | ON CONFLICT appends new entry via json_insert |
| AC20 | D4 | Each history entry includes all six fields |
| AC21 | D2 | Migration merges duplicates; one row per slug after completion |
| AC22 | D2 | Merged row cost_usd = sum of all original rows |
| AC23 | D2 | Merged row duration_s = sum of all original rows |
| AC24 | D2 | Merged row outcome from row with latest finished_at |
| AC25 | D2 | Merged row finished_at = MAX(finished_at) across all rows |
| AC26 | D2 | Merged row run_id/tokens_per_minute/verification_notes from latest |
| AC27 | D2 | attempts_history built from all rows ordered by finished_at |
| AC28 | D2 | All extra rows deleted; only merged row remains |
| AC29 | D2 | Migration runs in _init_db, adds column and merges duplicates |
| AC30 | D2 | Idempotent: no-op if no duplicates and history already populated |
| AC31 | D3 | CREATE UNIQUE INDEX on slug added after migration |
| AC32 | D3 | Duplicate INSERT raises sqlite3.IntegrityError |
| AC33 | D5 | Queries return one row per slug with latest outcome/fields |
| AC34 | D5 | cost_usd in DB is accumulated sum; dashboard reads it directly |
| AC35 | D5 | duration_s in DB is accumulated sum; dashboard reads it directly |
| AC36 | D6 | UI drill-down exposes per-attempt history from attempts_history |
