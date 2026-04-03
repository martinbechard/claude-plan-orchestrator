# Structured Requirements: 85 Completions Upsert By Slug

Source: tmp/plans/.claimed/85-completions-upsert-by-slug.md
Generated: 2026-03-31T20:47:12.495919+00:00

## Requirements

### P1: Duplicate completion rows created on retry
Type: functional
Priority: high
Source clauses: [C1, C2, C27]
Description: When the pipeline retries a work item (after a warn or fail outcome), the `record_completion` method inserts a new row in the completions table instead of updating the existing one. This is because `record_completion` lacks upsert logic — it does not check if a completion record for that slug already exists before inserting. The result is duplicate entries in the dashboard for the same item.
Acceptance Criteria:
- After retrying a work item, does the completions table still contain exactly one row for that slug? YES = pass, NO = fail
- Does calling `record_completion` for an already-existing slug update the existing row rather than insert a new one? YES = pass, NO = fail

### P2: No uniqueness constraint on slug column
Type: functional
Priority: high
Source clauses: [C29, C32]
Description: The completions table lacks a UNIQUE constraint on the slug column. This allows continued duplicate insertion on retries and violates the single-source-of-truth invariant that the table should maintain one row per slug.
Acceptance Criteria:
- Does the completions table schema include a UNIQUE constraint on the slug column? YES = pass, NO = fail
- Does attempting to INSERT a row with an existing slug raise a constraint violation (unless handled by upsert)? YES = pass, NO = fail

### P3: Dashboard displays confusing duplicate entries
Type: UI
Priority: high
Source clauses: [C30]
Description: Multiple rows per slug in the completions table cause the dashboard to display duplicate entries for the same work item, confusing users who expect to see one summary per item.
Acceptance Criteria:
- Does the dashboard show exactly one row per slug? YES = pass, NO = fail

### P4: Duplicate rows waste storage
Type: non-functional
Priority: low
Source clauses: [C31]
Description: Accumulating duplicate rows for each retry wastes database storage, as only the merged summary row and its attempt history are needed.
Acceptance Criteria:
- After migration, do all slugs have at most one row in the completions table? YES = pass, NO = fail

### FR1: Upsert logic in record_completion with accumulated totals
Type: functional
Priority: high
Source clauses: [C3, C4, C5, C6, C7, C8, C9, C10, C11, C12, C24]
Description: The `record_completion` method in `langgraph_pipeline/web/proxy.py` must implement upsert (INSERT ... ON CONFLICT) logic keyed on the slug column. On conflict, the method must:
- **Accumulate** `cost_usd`: add the new attempt's cost to the existing total (the money was already spent).
- **Accumulate** `duration_s`: add the new attempt's duration to the existing total (total wall-clock time invested).
- **Replace** `outcome`: set to the latest attempt's outcome (success/warn/fail).
- **Replace** `finished_at`: set to the latest attempt's timestamp.
- **Replace** `run_id`: set to the latest attempt's trace ID.
- **Replace** `tokens_per_minute`: set to the latest attempt's velocity.
- **Replace** `verification_notes`: set to the latest attempt's notes.

On first insert (no conflict), the row is created normally with the single attempt's values.
Acceptance Criteria:
- On first completion for a slug, is a single row inserted with the attempt's values? YES = pass, NO = fail
- On a second completion for the same slug, is `cost_usd` equal to the sum of both attempts? YES = pass, NO = fail
- On a second completion for the same slug, is `duration_s` equal to the sum of both attempts? YES = pass, NO = fail
- On a second completion, does `outcome` reflect the latest attempt's value? YES = pass, NO = fail
- On a second completion, does `finished_at` reflect the latest attempt's timestamp? YES = pass, NO = fail
- On a second completion, does `run_id` reflect the latest attempt's trace ID? YES = pass, NO = fail
- On a second completion, does `tokens_per_minute` reflect the latest attempt's velocity? YES = pass, NO = fail
- On a second completion, does `verification_notes` reflect the latest attempt's notes? YES = pass, NO = fail

### FR2: Attempts history tracking
Type: functional
Priority: high
Source clauses: [C13, C14]
Description: Add an `attempts_history` column (JSON array) to the completions table. Each call to `record_completion` must append an entry to this array containing: `outcome`, `cost_usd`, `duration_s`, `finished_at`, `run_id`, and `tokens_per_minute`. This preserves a history of all attempts so the user can see every stop and restart. On first insert, the array contains one entry. On upsert, the new attempt is appended to the existing array.
Acceptance Criteria:
- Does the completions table have an `attempts_history` column? YES = pass, NO = fail
- After a first completion, does `attempts_history` contain a JSON array with exactly one entry? YES = pass, NO = fail
- After a retry, does `attempts_history` contain entries for both attempts in chronological order? YES = pass, NO = fail
- Does each entry in `attempts_history` include outcome, cost_usd, duration_s, finished_at, run_id, and tokens_per_minute? YES = pass, NO = fail

### FR3: Migration to merge existing duplicates and enforce uniqueness
Type: functional
Priority: high
Source clauses: [C16, C17, C18, C19, C20, C21, C22, C23, C25, C32]
Description: Existing data has multiple rows per slug. The migration (in `langgraph_pipeline/web/proxy.py` — `_ensure_tables` or a migration path) must:
1. Add the `attempts_history` column to the completions table if it does not exist.
2. For each slug with multiple rows, merge them into a single row:
   - `cost_usd` = sum of all rows for that slug.
   - `duration_s` = sum of all rows for that slug.
   - `outcome`, `finished_at`, `run_id`, `tokens_per_minute`, `verification_notes` = values from the row with the latest `finished_at`.
   - `attempts_history` = JSON array built from all rows for that slug, ordered by `finished_at`.
3. Delete the extra rows, keeping only the merged one.
4. Add a UNIQUE constraint on the slug column to prevent future duplicates.
Acceptance Criteria:
- After migration, does every slug have exactly one row? YES = pass, NO = fail
- For a slug that had 3 rows, is the merged `cost_usd` the sum of all 3 original rows' costs? YES = pass, NO = fail
- For a slug that had 3 rows, is the merged `duration_s` the sum of all 3 original rows' durations? YES = pass, NO = fail
- Does the merged row's `outcome` match the row with the latest `finished_at`? YES = pass, NO = fail
- Does the merged row's `finished_at` match the latest original row? YES = pass, NO = fail
- Does `attempts_history` contain entries for all original rows, ordered by `finished_at`? YES = pass, NO = fail
- Is a UNIQUE constraint present on the slug column after migration? YES = pass, NO = fail
- Does the migration handle slugs that already have only one row without error? YES = pass, NO = fail

### UC1: View accumulated totals with attempt history drill-down
Type: UI
Priority: medium
Source clauses: [C15, C26]
Description: The dashboard displays the summary row per slug with accumulated `cost_usd` and `duration_s` totals, the latest outcome, and optionally exposes the attempt history so the user can drill down to see each individual attempt's details.
Acceptance Criteria:
- Does the dashboard display the accumulated (summed) cost and duration per slug? YES = pass, NO = fail
- Can the user access the attempt history for a given slug from the dashboard? YES = pass, NO = fail
- Does the attempt history show individual attempt details (outcome, cost, duration, timestamp, run_id, tokens_per_minute)? YES = pass, NO = fail

---

## Coverage Matrix
| Raw Input Section | Requirement(s) |
|---|---|
| "record_completion inserts a new row... creates duplicate entries" | P1 |
| "completions table should have one row per slug" | FR1 |
| "On retry, the existing row is updated rather than a new row inserted" | FR1 |
| "record must accumulate totals from all attempts" (cost, duration, outcome, etc.) | FR1 |
| "record must maintain a history of all attempts" | FR2 |
| "Add an attempts_history column (JSON array)" | FR2 |
| "dashboard can show summary row... allow drilling down into attempt history" | UC1 |
| "Existing data has multiple rows per slug" | FR3 |
| Migration merge steps (sum cost/duration, latest outcome, build JSON array) | FR3 |
| "Delete the extra rows, keeping only the merged one" | FR3 |
| "Add a UNIQUE constraint on the slug column" | P2, FR3 |
| "proxy.py - record_completion method: on conflict (slug), accumulate..." | FR1, FR2 |
| "proxy.py - _ensure_tables / migration" | FR3 |
| "Dashboard display: show accumulated cost/duration, optionally expose attempt history" | UC1 |
| "record_completion method lacks upsert logic" | P1 |
| "Multiple rows violate the single source of truth" | P2 |
| "Multiple rows confuse the dashboard" | P3 |
| "Multiple rows waste storage" | P4 |
| "completions table lacks a UNIQUE constraint on slug" | P2, FR3 |
| "original implementation assumed each record_completion call would write a new slug" | (context, see C28) |

## Clause Coverage Grid
| Clause | Type | Mapped To | Status |
|---|---|---|---|
| C1 [FACT] | FACT | P1 | Mapped |
| C2 [PROB] | PROB | P1 | Mapped |
| C3 [GOAL] | GOAL | FR1 | Mapped |
| C4 [GOAL] | GOAL | FR1 | Mapped |
| C5 [CONS] | CONS | FR1 | Mapped |
| C6 [CONS] | CONS | FR1 | Mapped |
| C7 [CONS] | CONS | FR1 | Mapped |
| C8 [CONS] | CONS | FR1 | Mapped |
| C9 [CONS] | CONS | FR1 | Mapped |
| C10 [CONS] | CONS | FR1 | Mapped |
| C11 [CONS] | CONS | FR1 | Mapped |
| C12 [CONS] | CONS | FR1 | Mapped |
| C13 [GOAL] | GOAL | FR2 | Mapped |
| C14 [AC] | AC | FR2 | Mapped |
| C15 [GOAL] | GOAL | UC1 | Mapped |
| C16 [FACT] | FACT | FR3 | Mapped |
| C17 [AC] | AC | FR3 | Mapped |
| C18 [AC] | AC | FR3 | Mapped |
| C19 [AC] | AC | FR3 | Mapped |
| C20 [AC] | AC | FR3 | Mapped |
| C21 [AC] | AC | FR3 | Mapped |
| C22 [AC] | AC | FR3 | Mapped |
| C23 [AC] | AC | P2, FR3 | Mapped |
| C24 [AC] | AC | FR1, FR2 | Mapped |
| C25 [AC] | AC | FR3 | Mapped |
| C26 [AC] | AC | UC1 | Mapped |
| C27 [FACT] | FACT | P1 | Mapped |
| C28 [CTX] | CTX | -- | Unmapped: context explaining original design assumption; informs P1 root cause but not a testable requirement |
| C29 [PROB] | PROB | P2 | Mapped |
| C30 [PROB] | PROB | P3 | Mapped |
| C31 [PROB] | PROB | P4 | Mapped |
| C32 [FACT] | FACT | P2, FR3 | Mapped |

## Validation

Status: ACCEPTED
Iterations: 1
Reviewer notes: ACCEPT


## Acceptance Criteria

**AC1**: After retrying a work item, does the completions table contain exactly one row for that slug? YES = pass, NO = fail
  Origin: Derived from C2 [PROB] (inverse: "creates duplicate entries" → "no duplicates exist")
  Belongs to: P1
  Source clauses: [C1, C2, C27]

**AC2**: Does calling `record_completion` for an already-existing slug update the existing row rather than insert a new one? YES = pass, NO = fail
  Origin: Derived from C4 [GOAL] (operationalized)
  Belongs to: P1, FR1
  Source clauses: [C4, C27]

**AC3**: Does the completions table schema include a UNIQUE constraint on the slug column? YES = pass, NO = fail
  Origin: Explicit from C23
  Belongs to: P2, FR3
  Source clauses: [C23, C32]

**AC4**: Does attempting to INSERT a row with an existing slug raise a constraint violation (unless handled by upsert)? YES = pass, NO = fail
  Origin: Derived from C29 [PROB] (inverse: "violate single source of truth" → "constraint enforces single source of truth")
  Belongs to: P2
  Source clauses: [C29, C32]

**AC5**: Does the dashboard show exactly one row per slug? YES = pass, NO = fail
  Origin: Derived from C30 [PROB] (inverse: "confuse the dashboard" → "dashboard shows one row")
  Belongs to: P3
  Source clauses: [C30]

**AC6**: After migration, do all slugs have at most one row in the completions table? YES = pass, NO = fail
  Origin: Derived from C31 [PROB] (inverse: "waste storage" → "no duplicate rows remain")
  Belongs to: P4, FR3
  Source clauses: [C31, C22]

**AC7**: On first completion for a slug, is a single row inserted with the attempt's values? YES = pass, NO = fail
  Origin: Derived from C3 [GOAL] (operationalized: "one row per slug" on initial insert)
  Belongs to: FR1
  Source clauses: [C3, C24]

**AC8**: On a second completion for the same slug, is `cost_usd` equal to the sum of both attempts' costs? YES = pass, NO = fail
  Origin: Explicit from C6 (operationalized via C24)
  Belongs to: FR1
  Source clauses: [C5, C6, C24]

**AC9**: On a second completion for the same slug, is `duration_s` equal to the sum of both attempts' durations? YES = pass, NO = fail
  Origin: Explicit from C7 (operationalized via C24)
  Belongs to: FR1
  Source clauses: [C5, C7, C24]

**AC10**: On a second completion for the same slug, does `outcome` reflect the latest attempt's value? YES = pass, NO = fail
  Origin: Explicit from C8 (operationalized via C24)
  Belongs to: FR1
  Source clauses: [C8, C24]

**AC11**: On a second completion for the same slug, does `finished_at` reflect the latest attempt's timestamp? YES = pass, NO = fail
  Origin: Explicit from C9 (operationalized via C24)
  Belongs to: FR1
  Source clauses: [C9, C24]

**AC12**: On a second completion for the same slug, does `run_id` reflect the latest attempt's trace ID? YES = pass, NO = fail
  Origin: Explicit from C10 (operationalized via C24)
  Belongs to: FR1
  Source clauses: [C10, C24]

**AC13**: On a second completion for the same slug, does `tokens_per_minute` reflect the latest attempt's velocity? YES = pass, NO = fail
  Origin: Explicit from C11 (operationalized via C24)
  Belongs to: FR1
  Source clauses: [C11, C24]

**AC14**: On a second completion for the same slug, does `verification_notes` reflect the latest attempt's notes? YES = pass, NO = fail
  Origin: Explicit from C12 (operationalized via C24)
  Belongs to: FR1
  Source clauses: [C12, C24]

**AC15**: Does the completions table have an `attempts_history` column? YES = pass, NO = fail
  Origin: Explicit from C14
  Belongs to: FR2, FR3
  Source clauses: [C14, C25]

**AC16**: After a first completion, does `attempts_history` contain a JSON array with exactly one entry? YES = pass, NO = fail
  Origin: Derived from C13 [GOAL] (operationalized: "maintain a history" → first entry exists)
  Belongs to: FR2
  Source clauses: [C13, C14]

**AC17**: After a retry, does `attempts_history` contain entries for both attempts in chronological order? YES = pass, NO = fail
  Origin: Derived from C13 [GOAL] (operationalized: "see every stop and restart")
  Belongs to: FR2
  Source clauses: [C13, C14, C24]

**AC18**: Does each entry in `attempts_history` include outcome, cost_usd, duration_s, finished_at, run_id, and tokens_per_minute? YES = pass, NO = fail
  Origin: Explicit from C14
  Belongs to: FR2
  Source clauses: [C14]

**AC19**: For a slug that had 3 existing rows, is the merged `cost_usd` the sum of all 3 original rows' costs? YES = pass, NO = fail
  Origin: Explicit from C18
  Belongs to: FR3
  Source clauses: [C17, C18]

**AC20**: For a slug that had 3 existing rows, is the merged `duration_s` the sum of all 3 original rows' durations? YES = pass, NO = fail
  Origin: Explicit from C19
  Belongs to: FR3
  Source clauses: [C17, C19]

**AC21**: Does the merged row's `outcome`, `finished_at`, `run_id`, `tokens_per_minute`, and `verification_notes` match the values from the row with the latest `finished_at`? YES = pass, NO = fail
  Origin: Explicit from C20
  Belongs to: FR3
  Source clauses: [C17, C20]

**AC22**: Does the migration build `attempts_history` as a JSON array from all original rows for a slug, ordered by `finished_at`? YES = pass, NO = fail
  Origin: Explicit from C21
  Belongs to: FR3
  Source clauses: [C21]

**AC23**: After merging, are the extra rows deleted so only the merged row remains per slug? YES = pass, NO = fail
  Origin: Explicit from C22
  Belongs to: FR3
  Source clauses: [C22]

**AC24**: Does the migration handle slugs that already have only one row without error? YES = pass, NO = fail
  Origin: Derived from C16 [FACT] (defensive: "existing data has multiple rows" implies some may not)
  Belongs to: FR3
  Source clauses: [C16, C25]

**AC25**: Does the `record_completion` method use INSERT ... ON CONFLICT (slug) to accumulate cost/duration and append to `attempts_history`? YES = pass, NO = fail
  Origin: Explicit from C24
  Belongs to: FR1, FR2
  Source clauses: [C24]

**AC26**: Is the migration implemented in `langgraph_pipeline/web/proxy.py` (`_ensure_tables` or migration path)? YES = pass, NO = fail
  Origin: Explicit from C25
  Belongs to: FR3
  Source clauses: [C25]

**AC27**: Does the dashboard display the accumulated (summed) cost and duration per slug? YES = pass, NO = fail
  Origin: Derived from C15 [GOAL] (operationalized: "show summary row with accumulated totals")
  Belongs to: UC1
  Source clauses: [C15, C26]

**AC28**: Can the user access the attempt history for a given slug from the dashboard? YES = pass, NO = fail
  Origin: Derived from C15 [GOAL] (operationalized: "allow drilling down into attempt history")
  Belongs to: UC1
  Source clauses: [C15, C26]

**AC29**: Does the attempt history display show individual attempt details (outcome, cost_usd, duration_s, finished_at, run_id, tokens_per_minute)? YES = pass, NO = fail
  Origin: Explicit from C26 (operationalized via C14 field list)
  Belongs to: UC1
  Source clauses: [C14, C26]

---

## Requirement -> AC Coverage

| Requirement | ACs | Count |
|---|---|---|
| P1 | AC1, AC2 | 2 |
| P2 | AC3, AC4 | 2 |
| P3 | AC5 | 1 |
| P4 | AC6 | 1 |
| FR1 | AC2, AC7, AC8, AC9, AC10, AC11, AC12, AC13, AC14, AC25 | 10 |
| FR2 | AC15, AC16, AC17, AC18, AC25 | 5 |
| FR3 | AC3, AC6, AC15, AC19, AC20, AC21, AC22, AC23, AC24, AC26 | 10 |
| UC1 | AC27, AC28, AC29 | 3 |

---

## Clause -> AC Coverage

| Clause | Type | AC | How |
|---|---|---|---|
| C1 | FACT | AC1 | Supports context for P1 (retry creates row) — tested via AC1's scenario |
| C2 | PROB | AC1 | Inverse ("duplicates created" → "exactly one row exists") |
| C3 | GOAL | AC7 | Operationalized ("one row per slug" → first insert creates single row) |
| C4 | GOAL | AC2 | Operationalized ("row is updated" → update not insert on conflict) |
| C5 | CONS | AC8, AC9 | Frame for accumulation — tested via AC8 (cost) and AC9 (duration) |
| C6 | CONS | AC8 | Explicit (cost_usd summed) |
| C7 | CONS | AC9 | Explicit (duration_s summed) |
| C8 | CONS | AC10 | Explicit (outcome = latest) |
| C9 | CONS | AC11 | Explicit (finished_at = latest) |
| C10 | CONS | AC12 | Explicit (run_id = latest) |
| C11 | CONS | AC13 | Explicit (tokens_per_minute = latest) |
| C12 | CONS | AC14 | Explicit (verification_notes = latest) |
| C13 | GOAL | AC16, AC17 | Operationalized ("maintain history" → array has entries after each attempt) |
| C14 | AC | AC15, AC16, AC17, AC18 | Explicit (column exists, entries contain required fields) |
| C15 | GOAL | AC27, AC28 | Operationalized ("show summary + drill-down" → dashboard displays totals, user can access history) |
| C16 | FACT | AC24 | Supports defensive test: migration handles single-row slugs |
| C17 | AC | AC19, AC20, AC21, AC22 | Explicit (merge into single row) |
| C18 | AC | AC19 | Explicit (cost_usd = sum) |
| C19 | AC | AC20 | Explicit (duration_s = sum) |
| C20 | AC | AC21 | Explicit (latest finished_at fields) |
| C21 | AC | AC22 | Explicit (attempts_history from all rows) |
| C22 | AC | AC23 | Explicit (delete extra rows) |
| C23 | AC | AC3 | Explicit (UNIQUE constraint on slug) |
| C24 | AC | AC25 | Explicit (ON CONFLICT upsert in record_completion) |
| C25 | AC | AC15, AC26 | Explicit (migration adds column, in proxy.py) |
| C26 | AC | AC27, AC28, AC29 | Explicit (dashboard shows totals, exposes history) |
| C27 | FACT | AC1, AC2 | Supports context for P1 (lacks upsert) — tested via AC1 and AC2 |
| C28 | CTX | -- | Context only: explains original design assumption; informs P1 root cause but not independently testable |
| C29 | PROB | AC4 | Inverse ("violates single source of truth" → "constraint prevents duplicates") |
| C30 | PROB | AC5 | Inverse ("confuses dashboard" → "dashboard shows one row per slug") |
| C31 | PROB | AC6 | Inverse ("wastes storage" → "no duplicate rows after migration") |
| C32 | FACT | AC3, AC4 | Supports context for P2 (no constraint exists) — tested via AC3 and AC4 |
