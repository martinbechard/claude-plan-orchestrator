# Design: Fix "Invalid Date" in Recent Completions Finished Column

## Problem

`fmtFinished()` in `dashboard.js` multiplies `finished_at` by 1000 assuming it is a
Unix timestamp (number). When the DB proxy path is active, `proxy.list_completions()`
returns `finished_at` as an ISO 8601 string. Multiplying a string by 1000 yields NaN,
which causes `new Date(NaN)` → "Invalid Date".

## Fix

Update `fmtFinished()` to branch on the type of its argument:

- If `typeof finishedAt === "number"`: treat as Unix epoch seconds → multiply by 1000.
- Otherwise: pass directly to `new Date()` (ISO 8601 strings are natively parsed).

## Key File

- `langgraph_pipeline/web/static/dashboard.js` — `fmtFinished()` at line 30.

## Design Decision

The fix is purely in the JS helper; no server-side changes are needed. Both the
in-memory path (float) and the DB proxy path (ISO string) are handled transparently
by a single type check.
