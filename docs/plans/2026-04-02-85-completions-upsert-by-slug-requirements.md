# Structured Requirements: 85 Completions Upsert By Slug

Source: tmp/plans/.claimed/85-completions-upsert-by-slug.md
Generated: 2026-04-02T18:26:26.716287+00:00

## Requirements

### P1: Duplicate rows created on retry instead of update
Type: functional
Priority: high
Source clauses: [C1, C2, C25, C27, C30]
Description: When the pipeline retries a work item (after a warn or fail outcome), record_completion inserts a new row in the completions table instead of updating the existing one. This creates duplicate entries in the dashboard for the same item, violating the single source of truth, confusing the dashboard, and wasting storage. The root cause is that record_completion lacks upsert logic -- it does not check if a completion record for that slug already exists before inserting.
Acceptance Criteria:
- Does retrying a work item after warn/fail produce a second row in the completions table? YES = fail, NO = pass
- Does the dashboard show duplicate entries for a retried item? YES = fail, NO = pass

### P2: Missing UNIQUE constraint on slug column
Type: functional
Priority: high
Source clauses: [C28]
Description: The completions table lacks a UNIQUE constraint on the slug column. Existing data already contains multiple rows per slug, and the schema allows continued duplicate insertion on retries. Without this constraint, even correct application-level upsert logic could be bypassed by concurrent inserts.
Acceptance Criteria:
- Does the completions table have a UNIQUE constraint on the slug column? YES = pass, NO = fail
- Does inserting a second row with the same slug raise a constraint violation at the database level? YES = pass, NO = fail

### FR1: Upsert logic in record_completion
Type: functional
Priority: high
Source clauses: [C3, C4, C5, C22, C29]
Description: The record_completion method in langgraph_pipeline/web/proxy.py must implement upsert (INSERT ... ON CONFLICT) logic keyed on the slug column. When a slug already exists, the existing row is updated rather than a new row inserted. The completions table must have exactly one row per slug representing the current state of that item. The upsert must accumulate totals from all attempts rather than replacing with the latest values only.
Acceptance Criteria:
- Does record_completion use ON CONFLICT (slug) upsert logic? YES = pass, NO = fail
- After two calls to record_completion with the same slug, is there exactly one row for that slug? YES = pass, NO = fail

### FR2: Accumulate cost_usd across attempts
Type: functional
Priority: high
Source clauses: [C5, C6]
Description: On upsert, cost_usd must be set to the sum of all attempts (the money was already spent). The accumulated value represents the total investment across every execution of that slug.
Acceptance Criteria:
- After two attempts costing $1.00 and $0.50, does the row show cost_usd = $1.50? YES = pass, NO = fail

### FR3: Accumulate duration_s across attempts
Type: functional
Priority: high
Source clauses: [C5, C7]
Description: On upsert, duration_s must be set to the sum of all attempts (total wall-clock time invested). The accumulated value represents the total time spent across every execution of that slug.
Acceptance Criteria:
- After two attempts of 120s and 90s, does the row show duration_s = 210? YES = pass, NO = fail

### FR4: Update outcome from latest attempt
Type: functional
Priority: high
Source clauses: [C5, C8]
Description: On upsert, the outcome field must be set to the latest attempt's outcome (success/warn/fail), replacing the previous value.
Acceptance Criteria:
- After a fail attempt followed by a success attempt, does the row show outcome = success? YES = pass, NO = fail

### FR5: Update finished_at from latest attempt
Type: functional
Priority: high
Source clauses: [C5, C9]
Description: On upsert, finished_at must be set to the latest attempt's timestamp, replacing the previous value.
Acceptance Criteria:
- After two attempts, does finished_at reflect the timestamp of the most recent attempt? YES = pass, NO = fail

### FR6: Update run_id from latest attempt
Type: functional
Priority: high
Source clauses: [C5, C10]
Description: On upsert, run_id must be set to the latest attempt's trace ID, replacing the previous value.
Acceptance Criteria:
- After two attempts, does run_id reflect the trace ID of the most recent attempt? YES = pass, NO = fail

### FR7: Update tokens_per_minute from latest attempt
Type: functional
Priority: medium
Source clauses: [C5, C11]
Description: On upsert, tokens_per_minute must be set to the latest attempt's velocity, replacing the previous value.
Acceptance Criteria:
- After two attempts, does tokens_per_minute reflect the value from the most recent attempt? YES = pass, NO = fail

### FR8: Update verification_notes from latest attempt
Type: functional
Priority: medium
Source clauses: [C5, C12]
Description: On upsert, verification_notes must be set to the latest attempt's notes, replacing the previous value.
Acceptance Criteria:
- After two attempts, does verification_notes reflect the notes from the most recent attempt? YES = pass, NO = fail

### FR9: Add attempts_history column with per-attempt entries
Type: functional
Priority: high
Source clauses: [C13, C14]
Description: A new attempts_history column (JSON array) must be added to the completions table. On each execution attempt, an entry is appended containing: outcome, cost_usd, duration_s, finished_at, run_id, and tokens_per_minute. This maintains a full history of all attempts so the user can see every stop and restart.
Acceptance Criteria:
- Does the completions table have an attempts_history column? YES = pass, NO = fail
- After three attempts, does attempts_history contain a JSON array with exactly three entries? YES = pass, NO = fail
- Does each entry in attempts_history contain outcome, cost_usd, duration_s, finished_at, run_id, and tokens_per_minute? YES = pass, NO = fail

### UC1: Dashboard shows accumulated totals with drill-down into attempt history
Type: UI
Priority: medium
Source clauses: [C15, C24]
Description: The dashboard must show the summary row with accumulated cost/duration totals and optionally expose the attempt history for drill-down. Users viewing the completions list see one row per slug with total cost_usd and total duration_s. Users can optionally drill down to see individual attempt details from the attempts_history JSON array.
Acceptance Criteria:
- Does the dashboard show exactly one row per slug? YES = pass, NO = fail
- Does the dashboard display accumulated cost_usd and duration_s totals? YES = pass, NO = fail
- Can the user drill down into the attempt history for a given slug? YES = pass, NO = fail

### FR10: Migration -- merge existing duplicate rows
Type: functional
Priority: high
Source clauses: [C16, C17, C18, C19, C20, C23]
Description: Existing data has multiple rows per slug. The migration in langgraph_pipeline/web/proxy.py (_ensure_tables or a dedicated migration) must: (1) For each slug with multiple rows, merge them into a single row where cost_usd = sum of all rows, duration_s = sum of all rows, and outcome/finished_at/run_id/tokens_per_minute/verification_notes come from the row with the latest finished_at. (2) Build an attempts_history JSON array from all rows ordered by finished_at. (3) Delete the extra rows, keeping only the merged one.
Acceptance Criteria:
- After migration, does each slug have exactly one row? YES = pass, NO = fail
- Is cost_usd the sum of all pre-migration rows for that slug? YES = pass, NO = fail
- Is duration_s the sum of all pre-migration rows for that slug? YES = pass, NO = fail
- Do outcome, finished_at, run_id, tokens_per_minute, verification_notes come from the row with latest finished_at? YES = pass, NO = fail
- Is attempts_history a JSON array built from all pre-migration rows ordered by finished_at? YES = pass, NO = fail
- Are all extra rows deleted after merging? YES = pass, NO = fail

### FR11: Add UNIQUE constraint on slug after migration
Type: functional
Priority: high
Source clauses: [C21, C29]
Description: After merging existing duplicates, the migration must add a UNIQUE constraint on the slug column to prevent future duplicates at the database level. This enforces the one-row-per-slug invariant going forward.
Acceptance Criteria:
- After migration, does the slug column have a UNIQUE constraint? YES = pass, NO = fail
- Does attempting to insert a duplicate slug fail with a constraint violation? YES = pass, NO = fail

---

## Coverage Matrix

| Raw Input Section | Requirement(s) |
|---|---|
| "When the pipeline retries...inserts a new row" | P1 |
| "This creates duplicate entries in the dashboard" | P1, UC1 |
| "one row per slug representing the current state" | FR1 |
| "On retry, the existing row is updated" | FR1 |
| "accumulate totals from all attempts" | FR2, FR3 |
| "cost_usd: sum of all attempts" | FR2 |
| "duration_s: sum of all attempts" | FR3 |
| "outcome: the latest attempt's outcome" | FR4 |
| "finished_at: the latest attempt's timestamp" | FR5 |
| "run_id: the latest attempt's trace ID" | FR6 |
| "tokens_per_minute: the latest attempt's velocity" | FR7 |
| "verification_notes: the latest attempt's notes" | FR8 |
| "maintain a history of all attempts" | FR9 |
| "Add an attempts_history column (JSON array)" | FR9 |
| "Dashboard can show summary...drill down" | UC1 |
| "Existing data has multiple rows per slug" | FR10 |
| "merge them into a single row" | FR10 |
| "Delete the extra rows, keeping only the merged one" | FR10 |
| "Add a UNIQUE constraint on slug" | FR11 |
| "record_completion method: on conflict (slug)" | FR1 |
| "_ensure_tables / migration" | FR10, FR11 |
| "Dashboard display: show accumulated cost/duration" | UC1 |
| "record_completion lacks upsert logic" | P1 |
| "original implementation assumed each call would write a new slug" | (context, see C26) |
| "multiple rows violate single source of truth" | P1 |
| "completions table lacks a UNIQUE constraint" | P2 |
| "Root Need: Enforce a strict one-row-per-slug invariant" | FR1, FR10, FR11 |
| "Summary: pipeline's retry mechanism creates duplicates" | P1 |

## Clause Coverage Grid

| Clause | Type | Mapped To | Status |
|---|---|---|---|
| C1 | PROB | P1 | Mapped |
| C2 | PROB | P1 | Mapped |
| C3 | GOAL | FR1 | Mapped |
| C4 | GOAL | FR1 | Mapped |
| C5 | GOAL | FR2, FR3, FR4, FR5, FR6, FR7, FR8 | Mapped |
| C6 | GOAL | FR2 | Mapped |
| C7 | GOAL | FR3 | Mapped |
| C8 | GOAL | FR4 | Mapped |
| C9 | GOAL | FR5 | Mapped |
| C10 | GOAL | FR6 | Mapped |
| C11 | GOAL | FR7 | Mapped |
| C12 | GOAL | FR8 | Mapped |
| C13 | GOAL | FR9 | Mapped |
| C14 | GOAL | FR9 | Mapped |
| C15 | GOAL | UC1 | Mapped |
| C16 | FACT | FR10 | Mapped |
| C17 | GOAL | FR10 | Mapped |
| C18 | GOAL | FR10 | Mapped |
| C19 | GOAL | FR10 | Mapped |
| C20 | GOAL | FR10 | Mapped |
| C21 | GOAL | FR11 | Mapped |
| C22 | GOAL | FR1 | Mapped |
| C23 | GOAL | FR10 | Mapped |
| C24 | GOAL | UC1 | Mapped |
| C25 | PROB | P1 | Mapped |
| C26 | CTX | -- | Unmapped: context only -- explains original design assumption |
| C27 | PROB | P1 | Mapped |
| C28 | PROB | P2 | Mapped |
| C29 | GOAL | FR1, FR11 | Mapped |
| C30 | PROB | P1 | Mapped |

## Validation

Status: ACCEPTED
Iterations: 1
Reviewer notes: ACCEPT


## Acceptance Criteria

AC1: After retrying a work item that previously completed with warn or fail, does the completions table contain exactly one row for that slug? YES = pass, NO = fail
  Origin: Derived from C1 [PROB] (inverse) + Derived from C3 [GOAL] (operationalized)
  Belongs to: P1
  Source clauses: [C1, C3]

AC2: After retrying a work item, does the dashboard show exactly one entry for that slug (no duplicates)? YES = pass, NO = fail
  Origin: Derived from C2 [PROB] (inverse)
  Belongs to: P1
  Source clauses: [C2, C27]

AC3: Does record_completion check for an existing row with the same slug before inserting? YES = pass, NO = fail
  Origin: Derived from C25 [PROB] (inverse)
  Belongs to: P1
  Source clauses: [C25, C30]

AC4: Does the completions table have a UNIQUE constraint on the slug column? YES = pass, NO = fail
  Origin: Derived from C28 [PROB] (inverse) + Derived from C21 [GOAL] (operationalized)
  Belongs to: P2
  Source clauses: [C21, C28]

AC5: Does inserting a second row with the same slug raise a database-level constraint violation? YES = pass, NO = fail
  Origin: Derived from C28 [PROB] (inverse)
  Belongs to: P2
  Source clauses: [C28]

AC6: Does record_completion use INSERT ... ON CONFLICT (slug) upsert logic? YES = pass, NO = fail
  Origin: Derived from C4 [GOAL] (operationalized) + Derived from C22 [GOAL] (operationalized)
  Belongs to: FR1
  Source clauses: [C4, C22, C29]

AC7: After two calls to record_completion with the same slug, is there exactly one row for that slug in the completions table? YES = pass, NO = fail
  Origin: Derived from C3 [GOAL] (operationalized)
  Belongs to: FR1
  Source clauses: [C3, C4]

AC8: After two attempts costing $1.00 and $0.50 for the same slug, does the row show cost_usd = $1.50 (sum of all attempts)? YES = pass, NO = fail
  Origin: Derived from C6 [GOAL] (operationalized)
  Belongs to: FR2
  Source clauses: [C5, C6]

AC9: After two attempts of 120s and 90s for the same slug, does the row show duration_s = 210 (sum of all attempts)? YES = pass, NO = fail
  Origin: Derived from C7 [GOAL] (operationalized)
  Belongs to: FR3
  Source clauses: [C5, C7]

AC10: After a fail attempt followed by a success attempt for the same slug, does the row show outcome = success? YES = pass, NO = fail
  Origin: Derived from C8 [GOAL] (operationalized)
  Belongs to: FR4
  Source clauses: [C5, C8]

AC11: After two attempts for the same slug, does finished_at reflect the timestamp of the most recent attempt? YES = pass, NO = fail
  Origin: Derived from C9 [GOAL] (operationalized)
  Belongs to: FR5
  Source clauses: [C5, C9]

AC12: After two attempts for the same slug, does run_id reflect the trace ID of the most recent attempt? YES = pass, NO = fail
  Origin: Derived from C10 [GOAL] (operationalized)
  Belongs to: FR6
  Source clauses: [C5, C10]

AC13: After two attempts for the same slug, does tokens_per_minute reflect the value from the most recent attempt? YES = pass, NO = fail
  Origin: Derived from C11 [GOAL] (operationalized)
  Belongs to: FR7
  Source clauses: [C5, C11]

AC14: After two attempts for the same slug, does verification_notes reflect the notes from the most recent attempt? YES = pass, NO = fail
  Origin: Derived from C12 [GOAL] (operationalized)
  Belongs to: FR8
  Source clauses: [C5, C12]

AC15: Does the completions table have an attempts_history column? YES = pass, NO = fail
  Origin: Derived from C14 [GOAL] (operationalized)
  Belongs to: FR9
  Source clauses: [C14]

AC16: After three attempts for the same slug, does attempts_history contain a JSON array with exactly three entries? YES = pass, NO = fail
  Origin: Derived from C13 [GOAL] (operationalized)
  Belongs to: FR9
  Source clauses: [C13, C14]

AC17: Does each entry in attempts_history contain all six fields: outcome, cost_usd, duration_s, finished_at, run_id, and tokens_per_minute? YES = pass, NO = fail
  Origin: Derived from C14 [GOAL] (operationalized)
  Belongs to: FR9
  Source clauses: [C14]

AC18: Does the dashboard show exactly one row per slug in the completions list? YES = pass, NO = fail
  Origin: Derived from C15 [GOAL] (operationalized)
  Belongs to: UC1
  Source clauses: [C15, C24]

AC19: Does the dashboard display accumulated (summed) cost_usd and duration_s totals for each slug? YES = pass, NO = fail
  Origin: Derived from C24 [GOAL] (operationalized)
  Belongs to: UC1
  Source clauses: [C15, C24]

AC20: Can the user drill down from a dashboard row to view individual attempt history entries? YES = pass, NO = fail
  Origin: Derived from C15 [GOAL] (operationalized)
  Belongs to: UC1
  Source clauses: [C15, C24]

AC21: After migration, does each slug that previously had multiple rows now have exactly one row? YES = pass, NO = fail
  Origin: Derived from C17 [GOAL] (operationalized) + Derived from C20 [GOAL] (operationalized)
  Belongs to: FR10
  Source clauses: [C16, C17, C20]

AC22: After migration, is cost_usd for each merged slug equal to the sum of cost_usd from all pre-migration rows for that slug? YES = pass, NO = fail
  Origin: Derived from C17 [GOAL] (operationalized)
  Belongs to: FR10
  Source clauses: [C17]

AC23: After migration, is duration_s for each merged slug equal to the sum of duration_s from all pre-migration rows for that slug? YES = pass, NO = fail
  Origin: Derived from C17 [GOAL] (operationalized)
  Belongs to: FR10
  Source clauses: [C17]

AC24: After migration, do outcome, finished_at, run_id, tokens_per_minute, and verification_notes for each merged slug come from the pre-migration row with the latest finished_at? YES = pass, NO = fail
  Origin: Derived from C18 [GOAL] (operationalized)
  Belongs to: FR10
  Source clauses: [C18]

AC25: After migration, is attempts_history for each merged slug a JSON array built from all pre-migration rows ordered by finished_at ascending? YES = pass, NO = fail
  Origin: Derived from C19 [GOAL] (operationalized)
  Belongs to: FR10
  Source clauses: [C19]

AC26: After migration, are all extra (duplicate) rows deleted, leaving only the single merged row per slug? YES = pass, NO = fail
  Origin: Derived from C20 [GOAL] (operationalized)
  Belongs to: FR10
  Source clauses: [C20]

AC27: Is the migration implemented in langgraph_pipeline/web/proxy.py (_ensure_tables or a dedicated migration function)? YES = pass, NO = fail
  Origin: Derived from C23 [GOAL] (operationalized)
  Belongs to: FR10
  Source clauses: [C23]

AC28: After migration completes, does the slug column have a UNIQUE constraint enforced at the database level? YES = pass, NO = fail
  Origin: Derived from C21 [GOAL] (operationalized) + Derived from C29 [GOAL] (operationalized)
  Belongs to: FR11
  Source clauses: [C21, C29]

AC29: After migration, does attempting to insert a row with a duplicate slug fail with a constraint violation? YES = pass, NO = fail
  Origin: Derived from C21 [GOAL] (operationalized)
  Belongs to: FR11
  Source clauses: [C21, C29]

---

## Requirement -> AC Coverage

| Requirement | ACs | Count |
|---|---|---|
| P1 | AC1, AC2, AC3 | 3 |
| P2 | AC4, AC5 | 2 |
| FR1 | AC6, AC7 | 2 |
| FR2 | AC8 | 1 |
| FR3 | AC9 | 1 |
| FR4 | AC10 | 1 |
| FR5 | AC11 | 1 |
| FR6 | AC12 | 1 |
| FR7 | AC13 | 1 |
| FR8 | AC14 | 1 |
| FR9 | AC15, AC16, AC17 | 3 |
| UC1 | AC18, AC19, AC20 | 3 |
| FR10 | AC21, AC22, AC23, AC24, AC25, AC26, AC27 | 7 |
| FR11 | AC28, AC29 | 2 |

## Clause -> AC Coverage

| Clause | Type | AC | How |
|---|---|---|---|
| C1 | PROB | AC1 | Inverse |
| C2 | PROB | AC2 | Inverse |
| C3 | GOAL | AC1, AC7 | Made testable |
| C4 | GOAL | AC6, AC7 | Made testable |
| C5 | GOAL | AC8, AC9, AC10, AC11, AC12, AC13, AC14 | Made testable (decomposed per sub-field) |
| C6 | GOAL | AC8 | Made testable |
| C7 | GOAL | AC9 | Made testable |
| C8 | GOAL | AC10 | Made testable |
| C9 | GOAL | AC11 | Made testable |
| C10 | GOAL | AC12 | Made testable |
| C11 | GOAL | AC13 | Made testable |
| C12 | GOAL | AC14 | Made testable |
| C13 | GOAL | AC16 | Made testable |
| C14 | GOAL | AC15, AC16, AC17 | Made testable |
| C15 | GOAL | AC18, AC19, AC20 | Made testable |
| C16 | FACT | AC21 | -- Precondition for FR10; testable via migration outcome |
| C17 | GOAL | AC21, AC22, AC23 | Made testable |
| C18 | GOAL | AC24 | Made testable |
| C19 | GOAL | AC25 | Made testable |
| C20 | GOAL | AC21, AC26 | Made testable |
| C21 | GOAL | AC4, AC28, AC29 | Made testable |
| C22 | GOAL | AC6 | Made testable |
| C23 | GOAL | AC27 | Made testable |
| C24 | GOAL | AC18, AC19, AC20 | Made testable |
| C25 | PROB | AC3 | Inverse |
| C26 | CTX | -- | Context only -- explains original design assumption; not independently testable |
| C27 | PROB | AC2 | Inverse (subsumed by dashboard duplicate check) |
| C28 | PROB | AC4, AC5 | Inverse |
| C29 | GOAL | AC6, AC28, AC29 | Made testable (root need decomposed into upsert + constraint ACs) |
| C30 | PROB | AC3 | Inverse (summary clause; subsumed by upsert existence check) |
