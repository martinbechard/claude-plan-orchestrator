# 07 - Completions Paged Table: Design

## Status

Previously implemented. This plan verifies the existing implementation and fixes
any gaps found during validation.

## Architecture Overview

The completions page provides a paginated, filterable view of all work-item
completion records stored in the SQLite database. It complements the dashboard's
live SSE-driven Recent Completions panel (limited to ~20 items) by offering full
historical access.

### Existing Components

All components are already in place:

- **Route**: langgraph_pipeline/web/routes/completions.py
  - GET /completions with query params: page, page_size, slug, outcome, date_from, date_to
  - Returns paginated rows with summary stats (total, success/warn/fail counts, cost)
  - Registered in server.py

- **Template**: langgraph_pipeline/web/templates/completions.html
  - Summary stats bar (total, success, warn, fail, cost)
  - Filter bar (slug substring, outcome select, date range)
  - Table: Slug (linked to /item/<slug>), Trace, Type, Outcome badge, Cost, Duration, Velocity, Finished At
  - Pagination controls preserving filter state
  - Empty state with filter-aware messaging

- **Proxy methods** (langgraph_pipeline/web/proxy.py):
  - list_completions(page, page_size, slug, outcome, date_from, date_to)
  - count_completions(slug, outcome, date_from, date_to)
  - sum_completions_cost(slug, outcome, date_from, date_to)

- **Dashboard integration**: "View all" link in Recent Completions panel links to /completions

## Plan

Since all code exists, the plan consists of a single task: verify the page loads
correctly, filters work, pagination works, and the "View all" link navigates
properly. Fix any issues found.

## Design Decisions

- Page size default: 50 rows (configurable via query param, max 500)
- Filters combine with AND logic
- Summary stats reflect active filters
- Slug links to /item/<slug> for drill-down
- Pagination preserves all active filter params in URLs
