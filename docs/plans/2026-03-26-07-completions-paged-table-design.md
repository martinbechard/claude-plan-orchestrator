# Completions Paginated Table — Design

## Overview

Add a `/completions` page showing the full history of work-item completions with
pagination, filters, and summary stats. The dashboard Recent Completions panel
gains a "View all" link to this page.

## Architecture

### Backend

**`langgraph_pipeline/web/proxy.py`** — extend `TracingProxy`:

- `count_completions(slug, outcome, date_from, date_to) -> int` — COUNT query
  with the same optional filters as `list_completions`.
- `list_completions(page, page_size, slug, outcome, date_from, date_to)` —
  extend the existing method (currently takes only `limit`) with `offset` and
  the four filter parameters.  The dashboard path calls it with the existing
  default `limit=COMPLETIONS_LIMIT`; the new route passes explicit pagination
  params.
- `sum_completions_cost(slug, outcome, date_from, date_to) -> float` — SUM
  cost_usd for the same filter set, used for the summary stats.

**`langgraph_pipeline/web/routes/completions.py`** — new router:

- `GET /completions` — renders `completions.html`; query params: `page` (int,
  default 1), `page_size` (int, default 50), `slug` (str), `outcome` (str),
  `date_from` (str ISO date), `date_to` (str ISO date).
- Passes to template: `rows`, `page`, `total_pages`, `slug`, `outcome`,
  `date_from`, `date_to`, `total_count`, `success_count`, `warn_count`,
  `fail_count`, `total_cost_usd`.

Register router in **`langgraph_pipeline/web/server.py`**.

### Frontend

**`langgraph_pipeline/web/templates/completions.html`** — new page:

- Extends `base.html`.
- Summary stats bar at top: total, success/warn/fail counts, total cost.
- Filter bar: slug substring, outcome dropdown (all/success/warn/fail), date
  range inputs.  Submit on change or form submit.
- Paginated table columns: Slug (link to `/item/<slug>`), Type, Outcome (badge),
  Cost, Duration, Finished At.
- Pagination controls consistent with `proxy_list.html`.

**`langgraph_pipeline/web/templates/dashboard.html`** — small change:

- Add "View all" link below the Recent Completions panel pointing to
  `/completions`.

## Key Design Decisions

- `COMPLETIONS_LIMIT` constant in `proxy.py` is left unchanged; it controls
  only the dashboard SSE feed.  The new `/completions` route bypasses it.
- Summary stats (totals by outcome, total cost) are computed with dedicated SQL
  queries that respect the active filters so the stats always match the visible
  rows.
- Pagination style mirrors `proxy_list.html` for UI consistency.
- Each slug cell links to `/item/<slug>` (feature 06).
