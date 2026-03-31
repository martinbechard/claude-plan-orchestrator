# Design: 85 Completions Upsert By Slug

Source: tmp/plans/.claimed/85-completions-upsert-by-slug.md
Requirements: docs/plans/2026-03-31-85-completions-upsert-by-slug-requirements.md

## Architecture Overview

The completions table in proxy.py lacks a UNIQUE constraint on slug and uses
a plain INSERT in record_completion. When the supervisor retries a work item
(warn/fail outcome), each attempt inserts a new row, producing duplicates.

The fix has three parts, all in langgraph_pipeline/web/proxy.py:

1. A startup migration that deduplicates existing rows (keeping the one with
   the latest finished_at per slug) and deletes the rest.
2. A UNIQUE index on the slug column, added after deduplication.
3. An INSERT ... ON CONFLICT(slug) DO UPDATE in record_completion that
   overwrites the existing row with the latest attempt's values.

No UI changes are required. Once the database enforces one-row-per-slug, the
existing dashboard queries (list_completions, list_completions_grouped) naturally
return a single entry per slug. The completion_grouping module continues to work
correctly (attempt_count=1, retries=[]) and can be simplified in a future cleanup.

## Key Files to Modify

- langgraph_pipeline/web/proxy.py -- migration SQL, _init_db, record_completion
- tests/langgraph/web/test_proxy.py -- new tests for upsert and migration

## Design Decisions

### D1: Deduplicate existing completion rows at startup

Addresses: FR2
Satisfies: AC7, AC8, AC9, AC10
Approach: Add a SQL constant _DEDUPLICATE_COMPLETIONS_SQL that, for each slug
with multiple rows, deletes all rows except the one with the latest finished_at
(highest id as tiebreaker). This follows the existing pattern used for traces
deduplication (_DEDUPLICATE_RUN_IDS_SQL). Run this SQL in _init_db before
creating the unique index.
Files: langgraph_pipeline/web/proxy.py

### D2: Add UNIQUE constraint on slug column

Addresses: FR3
Satisfies: AC11, AC12
Approach: Add a SQL constant for CREATE UNIQUE INDEX IF NOT EXISTS
idx_completions_slug_unique ON completions (slug). Execute it in _init_db
after the deduplication migration (D1). A raw INSERT with a duplicate slug
will raise sqlite3.IntegrityError, enforcing the constraint at the schema level.
Files: langgraph_pipeline/web/proxy.py

### D3: Upsert logic in record_completion

Addresses: FR1, P1
Satisfies: AC1, AC3, AC4, AC5, AC6
Approach: Replace the plain INSERT in record_completion with INSERT ... ON
CONFLICT(slug) DO UPDATE SET for all mutable columns (item_type, outcome,
cost_usd, duration_s, finished_at, run_id, tokens_per_minute,
verification_notes). This requires the UNIQUE constraint from D2 to be in
place. On first call for a slug, a new row is inserted. On subsequent calls,
the existing row is overwritten with the latest values.
Files: langgraph_pipeline/web/proxy.py

### D4: Dashboard shows single entry per slug (no code change)

Addresses: P2
Satisfies: AC2
Approach: No code change required. Once D1+D2+D3 are applied, the completions
table has at most one row per slug. The existing list_completions and
list_completions_grouped methods naturally return at most one entry per slug.
The completion_grouping module produces attempt_count=1 and retries=[] for
every slug, which is correct.
Files: (none -- verified by integration tests)

## Design -> AC Traceability

| AC | Design Decision(s) | Approach |
|---|---|---|
| AC1 | D3 | ON CONFLICT upsert prevents duplicate rows on retry |
| AC2 | D4 | No code change; DB has one row per slug, dashboard follows |
| AC3 | D3 | ON CONFLICT DO UPDATE overwrites outcome, cost, duration, etc. |
| AC4 | D3 | INSERT path handles new slugs; ON CONFLICT path handles existing |
| AC5 | D3 | Upsert ensures at most one row per slug after each call |
| AC6 | D3 | DO UPDATE SET overwrites all mutable fields with latest values |
| AC7 | D1 | Migration deletes all but latest-finished_at row per slug |
| AC8 | D1 | Surviving row is the one with MAX(finished_at) |
| AC9 | D1 | All older rows deleted by migration SQL |
| AC10 | D1 | Surviving row retains its original field values (no modification) |
| AC11 | D2 | CREATE UNIQUE INDEX on slug column |
| AC12 | D2 | Raw INSERT with duplicate slug raises IntegrityError |
