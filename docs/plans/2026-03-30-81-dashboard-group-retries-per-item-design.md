# Design: 81 Dashboard Group Retries Per Item

Source item: tmp/plans/.claimed/81-dashboard-group-retries-per-item.md
Requirements: docs/plans/2026-03-30-81-dashboard-group-retries-per-item-requirements.md

Phase 0 design entries:
- Systems: docs/plans/2026-03-30-81-dashboard-group-retries-per-item-design-1-systems.md
- UX: docs/plans/2026-03-30-81-dashboard-group-retries-per-item-design-ux.md
- Frontend: docs/plans/2026-03-30-81-frontend-design-3-retry-grouping.md

## Architecture Overview

The dashboard completions table currently renders one row per completion record.
When an item is retried (e.g. outcome=warn then outcome=success), the same slug
appears in multiple rows, looking like duplicates. This design adds a grouping
layer that consolidates rows sharing the same slug into a single top-level entry
showing the final (most recent) outcome, with an expandable sub-table revealing
the full retry history.

### Data flow

1. **Shared utility (completion_grouping.py)**: A pure function
   `group_completions_by_slug()` takes a flat list of completion dicts (sorted by
   finished_at DESC) and returns grouped entries. Each group has the primary
   (most recent) completion's fields plus `attempt_count` (int) and `retries`
   (list of prior-attempt dicts). This function is used by both the proxy and
   in-memory paths, ensuring identical semantics.
2. **Backend (proxy.py)**: New method `list_completions_grouped()` queries
   completions from SQLite, over-fetches (limit * 3) to capture retries, then
   passes through the shared grouping function.
3. **Backend (dashboard_state.py)**: The in-memory fallback path converts
   CompletionRecord instances to dicts and passes through the same grouping
   function. The proxy path calls `proxy.list_completions_grouped()` instead
   of `proxy.list_completions()`.
4. **SSE snapshot**: The `recent_completions` payload switches from flat list to
   grouped list. Each entry gains `attempt_count` (int) and `retries` (list of
   prior-attempt dicts with outcome, cost_usd, duration_s, finished_at, run_id).
5. **Frontend (dashboard.js)**: `renderCompletions()` renders grouped rows. Items
   with `attempt_count > 1` get a disclosure toggle and retry count badge.
   A `toggleRetryRows()` function inserts/removes sub-rows. Expanded state
   is preserved across SSE re-renders via an `expandedRetrySlugs` Set.
6. **Frontend (dashboard.html)**: Modified completion-row template with toggle
   button and retry badge. New `tpl-retry-row` template for sub-rows.
7. **Frontend (style.css)**: Styles for retry badge, disclosure toggle, and
   sub-rows with indentation and muted visual treatment.

### Scope boundaries

- The `/completions` paginated page is NOT in scope. It has its own route and
  template. Grouping there would require pagination redesign.
- Timeline view is NOT affected. Retries show as separate bars with
  outcome-colored borders, which is useful for temporal understanding.

### Key files to create/modify

| File | Action | Purpose |
|---|---|---|
| `langgraph_pipeline/web/completion_grouping.py` | CREATE | Shared `group_completions_by_slug()` utility |
| `langgraph_pipeline/web/proxy.py` | MODIFY | Add `list_completions_grouped()` method |
| `langgraph_pipeline/web/dashboard_state.py` | MODIFY | Use grouped completions in snapshot() |
| `langgraph_pipeline/web/static/dashboard.js` | MODIFY | Grouped rendering, toggle, sub-rows, state preservation |
| `langgraph_pipeline/web/templates/dashboard.html` | MODIFY | Add toggle button, retry badge, retry sub-row template |
| `langgraph_pipeline/web/static/style.css` | MODIFY | Retry grouping CSS styles |
| `tests/langgraph/web/test_completion_grouping.py` | CREATE | Unit tests for grouping utility |
| `tests/langgraph/web/test_dashboard_state.py` | MODIFY | Verify snapshot() returns grouped entries |

## Design Decisions

### D1: Shared grouping utility in completion_grouping.py
- **Addresses**: P1, FR1
- **Satisfies**: AC1, AC2, AC5, AC7, AC8
- **Approach**: Create `langgraph_pipeline/web/completion_grouping.py` with a pure
  function `group_completions_by_slug()`. Takes a flat completion list sorted by
  finished_at DESC, groups by slug. For each slug: first occurrence (most recent)
  becomes the primary entry with all its fields; subsequent occurrences become the
  `retries` list (oldest-first), each containing only: outcome, cost_usd,
  duration_s, finished_at, run_id. Adds `attempt_count` (total executions) to
  each grouped entry. Items with no retries get `attempt_count=1` and empty
  `retries=[]`. Limit is applied to grouped entries, not raw rows.
- **Files**: `langgraph_pipeline/web/completion_grouping.py` (NEW),
  `tests/langgraph/web/test_completion_grouping.py` (NEW)

### D2: Integrate grouping into proxy and dashboard_state
- **Addresses**: P1, P3, FR1
- **Satisfies**: AC1, AC2, AC5, AC6, AC7, AC8
- **Approach**: Add `list_completions_grouped()` to TracingProxy that queries
  completions with over-fetch (limit * 3) and passes rows through the D1 grouping
  function. In dashboard_state.py `snapshot()`, switch the proxy path from
  `proxy.list_completions()` to `proxy.list_completions_grouped()`. For the
  in-memory fallback path, convert CompletionRecord instances to dicts and pass
  through the same grouping function. The item count in the dashboard
  (`total_processed`) remains based on the internal counter (counts dispatches,
  not completions), which already counts logical items.
- **Files**: `langgraph_pipeline/web/proxy.py` (MODIFY),
  `langgraph_pipeline/web/dashboard_state.py` (MODIFY),
  `tests/langgraph/web/test_dashboard_state.py` (MODIFY)

### D3: Retry count badge and visual indicator
- **Addresses**: P2, FR1
- **Satisfies**: AC3, AC4, AC9
- **Approach**: Add a retry count badge ("x2", "x3") next to the outcome badge
  in the completions table. The badge uses a neutral gray palette (#e2e8f0 bg,
  #475569 text, 10px font, pill shape) so it does not compete with the outcome
  badge. The badge is only rendered when `attempt_count > 1`; items with no
  retries show no badge, no toggle, and no visual noise -- identical to before.
  A disclosure triangle button is prepended to the slug cell for retried items,
  providing a visual affordance that the row is expandable. These two indicators
  (badge + triangle) let users distinguish retried items from separate items at
  a glance without reading IDs.
- **Files**: `langgraph_pipeline/web/static/dashboard.js` (MODIFY),
  `langgraph_pipeline/web/templates/dashboard.html` (MODIFY),
  `langgraph_pipeline/web/static/style.css` (MODIFY)

### D4: Expandable retry history sub-rows
- **Addresses**: P2, UC1
- **Satisfies**: AC10, AC11, AC12, AC13, AC14
- **Approach**: When a grouped entry has `attempt_count > 1`, clicking the
  disclosure toggle inserts sub-rows after the primary row showing each prior
  attempt. Sub-rows are hidden by default (collapsed state) and show: outcome
  badge, cost, duration, finished timestamp, and trace link. Sub-rows use
  indented (padding-left: 36px), muted styling (bg: #f8fafc, reduced font size)
  to visually subordinate them. The toggle rotates 90 degrees when expanded
  (CSS transform). A module-level `expandedRetrySlugs` Set preserves expanded
  state across SSE re-renders. Keyboard accessibility: the toggle is a `<button>`
  element (natively focusable, Enter/Space activatable) with `aria-expanded`
  and `aria-label` attributes. Clicking again collapses sub-rows back to the
  grouped single-row view.
- **Files**: `langgraph_pipeline/web/static/dashboard.js` (MODIFY),
  `langgraph_pipeline/web/templates/dashboard.html` (MODIFY),
  `langgraph_pipeline/web/static/style.css` (MODIFY)

## Design -> AC Traceability Grid

| AC | Design Decision(s) | Approach |
|---|---|---|
| AC1 | D1, D2 | group_completions_by_slug() consolidates rows with the same slug into one entry; both proxy and in-memory paths use it |
| AC2 | D1, D2 | Primary entry is the most recent per slug (first in DESC order), showing the final outcome |
| AC3 | D3 | Retry count badge + disclosure triangle provide visual distinction from non-retried items at a glance |
| AC4 | D3 | Retry count badge only shown when attempt_count > 1; no badge, no toggle for non-retried items |
| AC5 | D1, D2 | Each unique slug appears exactly once in the grouped result; sub-rows hidden by default |
| AC6 | D1, D2 | total_processed counter counts dispatches (logical items); grouped completions show one row per slug |
| AC7 | D1, D2 | Grouping is automatic based on slug matching; no user action needed |
| AC8 | D1, D2, D4 | Grouped view is the default; sub-rows start with display:none |
| AC9 | D3 | Non-retried items (attempt_count=1) render identically to before: no badge, no toggle, no visual noise |
| AC10 | D4 | Single click on disclosure toggle reveals sub-rows; button element supports keyboard Enter/Space |
| AC11 | D4 | Each sub-row shows the outcome badge for that specific attempt |
| AC12 | D4 | Each sub-row shows the finished_at timestamp for that specific attempt |
| AC13 | D4 | Sub-rows start hidden (display:none); only revealed by explicit toggle interaction |
| AC14 | D4 | Clicking the toggle again removes sub-rows; expandedRetrySlugs Set tracks state for re-render preservation |
