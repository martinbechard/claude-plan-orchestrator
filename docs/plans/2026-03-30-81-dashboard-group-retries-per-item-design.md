# Design: 81 Dashboard Group Retries Per Item

Source item: tmp/plans/.claimed/81-dashboard-group-retries-per-item.md
Requirements: docs/plans/2026-03-30-81-dashboard-group-retries-per-item-requirements.md

## Architecture Overview

The dashboard completions table currently renders one row per completion record.
When an item is retried (e.g. outcome=warn then outcome=success), the same slug
appears in multiple rows, looking like duplicates. This design adds a grouping
layer that consolidates rows sharing the same slug into a single top-level entry
showing the final (most recent) outcome, with an expandable sub-table revealing
the full retry history.

### Data flow

1. **Backend (proxy.py)**: New method `list_completions_grouped()` queries completions
   grouped by slug. For each slug, returns the latest row as the "primary" record
   plus an `attempt_count` and a `retries` list containing prior attempts.
2. **Backend (dashboard_state.py)**: The in-memory fallback path (no proxy) groups
   its `recent_completions` list by slug using the same logic.
3. **SSE snapshot**: The `recent_completions` payload switches from flat list to
   grouped list. Each entry gains `attempt_count` (int) and `retries` (list of
   prior-attempt dicts with outcome, cost_usd, duration_s, finished_at, run_id).
4. **Frontend (dashboard.js)**: `renderCompletions()` renders grouped rows. Items
   with `attempt_count > 1` get a toggle control to expand/collapse the retry
   sub-rows. The top-level row shows the final outcome prominently.
5. **Frontend (dashboard.html)**: New template for retry sub-rows and toggle affordance.
6. **Frontend (style.css)**: Styles for the expandable retry rows and toggle icon.

### Scope boundaries

- The `/completions` paginated page is NOT in scope for this feature. It has its
  own route and template. Grouping there would require pagination redesign.
  This feature targets only the dashboard SSE-fed completions table.
- Timeline view is NOT affected. Retries already show as separate bars with
  outcome-colored borders, which is useful for temporal understanding.

## Design Decisions

### D1: Group completions by slug in the proxy query layer
- **Addresses**: P1, FR1
- **Satisfies**: AC1, AC2, AC3
- **Approach**: Add a `list_completions_grouped()` method to `TracingProxy` that
  queries completions ordered by `finished_at DESC`, then post-processes in Python
  to group rows by slug. The first row per slug (most recent) becomes the primary
  entry; remaining rows become the `retries` list. This avoids complex SQL while
  keeping the grouping logic testable.
- **Files**: `langgraph_pipeline/web/proxy.py`

### D2: Group in-memory completions in dashboard_state snapshot
- **Addresses**: P1, FR1
- **Satisfies**: AC1, AC2, AC3
- **Approach**: When the proxy is not available (in-memory fallback), the
  `snapshot()` method groups `recent_completions` by slug using the same
  algorithm: most-recent record per slug as primary, older records as retries.
  Extract grouping into a shared utility function usable by both paths.
- **Files**: `langgraph_pipeline/web/dashboard_state.py`

### D3: Display final outcome prominently on the grouped row
- **Addresses**: FR2
- **Satisfies**: AC4, AC5
- **Approach**: The top-level completion row already shows the outcome badge.
  Since D1/D2 ensure the primary record is the most recent, the existing
  `renderCompletions()` template already displays the correct final outcome.
  Add a retry count badge (e.g. "x2") next to the outcome badge so users can
  see at a glance that retries occurred, without needing to expand.
- **Files**: `langgraph_pipeline/web/static/dashboard.js`, `langgraph_pipeline/web/templates/dashboard.html`, `langgraph_pipeline/web/static/style.css`

### D4: Expandable retry history sub-rows
- **Addresses**: FR3
- **Satisfies**: AC6, AC7, AC8
- **Approach**: When a grouped entry has `attempt_count > 1`, the JS renders a
  clickable toggle (disclosure triangle) on the primary row. Clicking it reveals
  sub-rows beneath showing each prior attempt's outcome, cost, duration, and
  finished time. Sub-rows are hidden by default (collapsed state). The sub-rows
  use a slightly indented, muted style to visually distinguish them from
  top-level entries.
- **Files**: `langgraph_pipeline/web/static/dashboard.js`, `langgraph_pipeline/web/templates/dashboard.html`, `langgraph_pipeline/web/static/style.css`

## Design -> AC Traceability Grid

| AC | Design Decision(s) | Approach |
|---|---|---|
| AC1 | D1, D2 | Group by slug so retried items appear as single consolidated entry |
| AC2 | D1, D2 | Most-recent record per slug becomes the single top-level row |
| AC3 | D1, D2 | Prior attempts are nested under retries list, never shown as top-level rows |
| AC4 | D1, D2, D3 | Primary record is the latest execution; its outcome badge is the prominent status |
| AC5 | D3 | Outcome visible on the grouped row without any interaction; retry count badge provides additional context |
| AC6 | D4 | Toggle control expands to reveal sub-rows with per-attempt outcomes |
| AC7 | D4 | Sub-rows hidden by default; only visible after explicit toggle interaction |
| AC8 | D4 | Each sub-row shows attempt outcome, cost, duration, and timestamp |
