---
title: "Design: Traces List — trace_id Column and Filter"
date: 2026-03-26
defect: 05-traces-trace-id-column-and-filter
---

## Overview

The traces list currently shows name, start time, duration, cost, model, and status but
omits the trace ID (stored as `run_id` in the `traces` table). Users cannot identify
specific traces by ID or filter the list to a single trace. This design adds a truncated,
copyable trace_id column and a filter input that narrows the list by run_id prefix or
exact match.

## Architecture

No new database columns are required — `run_id` already stores the trace identifier.
Changes are isolated to three layers that already share a consistent filter pattern:

- **Backend data layer** (`langgraph_pipeline/web/proxy.py`): extend `list_runs()` and
  `count_runs()` to accept a `trace_id` parameter and filter with `run_id LIKE ?`.

- **Route/controller layer** (`langgraph_pipeline/web/routes/proxy.py`): accept `trace_id`
  as a Query parameter, pass it to the proxy methods, and forward it to the template context.

- **Template layer** (`langgraph_pipeline/web/templates/proxy_list.html`): add a trace_id
  filter input to the filter form, add a trace_id column to the table header and body rows,
  and include trace_id in pagination link query strings.

## Key Files

| File | Change |
|------|--------|
| `langgraph_pipeline/web/proxy.py` | Add `trace_id` param to `list_runs()` and `count_runs()`; append `run_id LIKE ?` condition when non-empty |
| `langgraph_pipeline/web/routes/proxy.py` | Add `trace_id: str = Query(default="")` to `proxy_list()`; thread through to proxy calls and template context |
| `langgraph_pipeline/web/templates/proxy_list.html` | Add trace_id filter input; add Trace ID table column (truncated, monospace, `title` = full ID, copy button) |
| `tests/langgraph/web/test_proxy.py` | Add unit tests for trace_id filter in `list_runs()` and `count_runs()` |

## Design Decisions

**Use `run_id LIKE ?` (prefix/substring match):** Users typically copy a partial ID from
a log. An exact match would be too brittle; substring search matches the existing `slug`
filter pattern and is consistent with the rest of the codebase.

**Display as truncated with full ID in title attribute:** The run_id is a UUID (36 chars).
Showing 8–12 characters with a `title` tooltip for the full value is consistent with
common trace UIs and avoids widening the table excessively.

**No new DB column or migration:** `run_id` is already indexed (`idx_traces_run_id`) and
stored on every row. A `LIKE '%?%'` filter on an indexed column is acceptably fast for
the dataset sizes in scope.

**Follow existing filter pattern exactly:** The `conditions`/`params` builder in
`list_runs()` and `count_runs()` already handles `slug`, `model`, `date_from`, and
`date_to`. Adding `trace_id` follows the same guard-and-append pattern, keeping both
methods symmetric and easy to review.

## Test Coverage

- `list_runs()` with `trace_id` prefix returns only matching rows
- `list_runs()` with `trace_id=""` returns all rows (no regression)
- `count_runs()` with `trace_id` filter returns correct count
- Existing tests must continue to pass unchanged
