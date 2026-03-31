# Completions table creates duplicate rows on retry instead of updating

When the pipeline retries a work item (after a warn or fail outcome), record_completion inserts a new row in the completions table. This creates duplicate entries in the dashboard for the same item.

## Expected behavior

The completions table should have one row per slug representing the current state of that item. On retry, the existing row is updated rather than a new row inserted.

The record must accumulate totals from all attempts, not just the latest:
- cost_usd: sum of all attempts (the money was already spent)
- duration_s: sum of all attempts (total wall-clock time invested)
- outcome: the latest attempt's outcome (success/warn/fail)
- finished_at: the latest attempt's timestamp
- run_id: the latest attempt's trace ID
- tokens_per_minute: the latest attempt's velocity
- verification_notes: the latest attempt's notes

Additionally, the record must maintain a history of all attempts so the user can see every stop and restart. Add an attempts_history column (JSON array) that appends an entry for each execution attempt with: outcome, cost_usd, duration_s, finished_at, run_id, and tokens_per_minute. The dashboard can show the summary row with accumulated totals and allow drilling down into the attempt history.

## Migration

Existing data has multiple rows per slug. The migration must:
1. For each slug with multiple rows, merge them into a single row:
   - cost_usd = sum of all rows
   - duration_s = sum of all rows
   - outcome, finished_at, run_id, tokens_per_minute, verification_notes = from the row with latest finished_at
   - attempts_history = JSON array built from all rows ordered by finished_at
2. Delete the extra rows, keeping only the merged one
3. Add a UNIQUE constraint on the slug column to prevent future duplicates

## Affected code

- langgraph_pipeline/web/proxy.py - record_completion method: on conflict (slug), accumulate cost/duration, append to attempts_history, update outcome and other fields from latest attempt
- langgraph_pipeline/web/proxy.py - _ensure_tables / migration: add attempts_history column, merge existing duplicates
- Dashboard display: show accumulated cost/duration, optionally expose attempt history

## LangSmith Trace: 5027569c-caa0-45ee-bb4b-ffcf5f6a3c81


## 5 Whys Analysis

Title: Completions table creates duplicate rows on retry instead of updating

Clarity: 5

5 Whys:

W1: Why does the dashboard show duplicate entries for items that are retried?
    Because: When the pipeline retries a work item (after a warn or fail outcome), record_completion inserts a new row in the completions table instead of updating the existing one. [C2, C3]

W2: Why does record_completion insert a new row instead of updating the existing one?
    Because: The record_completion method lacks upsert logic—it doesn't check if a completion record for that slug already exists before inserting a new row. [C2, C4]

W3: Why wasn't upsert logic implemented in the first place?
    Because: The original implementation assumed each record_completion call would write a new slug, not accounting for the retry behavior that causes the same slug to be processed multiple times. [C2] [ASSUMPTION]

W4: Why is this lack of deduplication problematic?
    Because: The completions table should maintain one row per slug, always reflecting the most recent execution state. Multiple rows violate the single source of truth, confuse the dashboard, and waste storage. [C6, C11]

W5: Why hasn't the database schema prevented this?
    Because: The completions table lacks a UNIQUE constraint on the slug column, and existing data already contains multiple rows per slug, allowing continued duplicate insertion on retries. [C7, C10]

Root Need: Enforce a strict one-row-per-slug invariant in the completions table by: (1) implementing upsert logic in record_completion to update existing rows with the latest outcome, cost, and duration on retry [C4, C5], (2) migrating existing duplicates by keeping only the latest finished_at row per slug [C8, C9, C11], and (3) adding a UNIQUE constraint on slug to prevent future duplicates [C10]. [C1, C3, C4, C6]

Summary: The pipeline's retry mechanism creates duplicate completion entries because record_completion lacks upsert logic and the database schema doesn't enforce slug uniqueness.
