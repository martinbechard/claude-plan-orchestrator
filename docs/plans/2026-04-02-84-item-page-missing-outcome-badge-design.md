# Design: 84 Item Page Missing Outcome Badge

Source: tmp/plans/.claimed/84-item-page-missing-outcome-badge.md
Requirements: docs/plans/2026-04-02-84-item-page-missing-outcome-badge-requirements.md

## Overview

The work item detail page shows status badges (item type, pipeline stage, velocity)
but does not display the completion outcome (success/warn/fail). The outcome data
already exists in the completions table via proxy.list_completions_by_slug() -- the
gap is purely in the rendering pipeline. This design adds an outcome badge as the
first element in the badge list, with corresponding CSS and dynamic-refresh support.

## Key Files

- langgraph_pipeline/web/routes/item.py -- outcome derivation helper, template context, dynamic JSON
- langgraph_pipeline/web/templates/item.html -- outcome badge markup, CSS styles, JS refresh handler
- tests/langgraph/web/test_item_outcome_badge.py -- unit tests for outcome derivation and endpoint

## Design Decisions

### D1: Derive overall outcome from latest completion record

Addresses: P1, P2, UC1
Satisfies: AC1, AC2, AC3
Approach: Add a helper function _derive_outcome(completions) in item.py that returns
the outcome string from the most recent completion record (by finished_at), or None
if no completions exist. This reuses the existing _load_completions() data already
fetched in both item_detail() and item_dynamic(). The function returns Optional[str]
-- one of "success", "warn", "fail", or None. The badge rendering logic retrieves
the outcome field from the completion record (AC2) and renders it as a visible badge
(AC3).
Files: langgraph_pipeline/web/routes/item.py

### D2: Pass outcome to template context and dynamic JSON

Addresses: P1, UC1
Satisfies: AC1, AC4
Approach: In item_detail(), call _derive_outcome(completions) and add "outcome" to
the template context dict. In item_dynamic(), also call _derive_outcome(completions)
and include "outcome" in the JSON response. This ensures the badge renders on initial
page load and updates during auto-refresh. The user can determine the outcome
immediately upon viewing the detail page without additional navigation (AC4).
Files: langgraph_pipeline/web/routes/item.py

### D3: Render outcome badge as first element in badge list

Addresses: FR1, UC1
Satisfies: AC1, AC4, AC5, AC6
Approach: In item.html, insert a new span before the item_type badge inside the
item-badges div. The badge uses data-dynamic="outcome-badge" wrapper. Render only
when outcome is not None -- when no completion record exists, the badge element is
empty. The badge text displays the outcome value (success/warn/fail), covering all
three values (AC6). Being the first child of item-badges makes it the leftmost
(most prominent) badge, appearing before all other status badges (AC5).
Files: langgraph_pipeline/web/templates/item.html

### D4: Add CSS styles for visual prominence and distinction

Addresses: FR1, FR2
Satisfies: AC6, AC7, AC8
Approach: Add three CSS classes: outcome-success (green: bg #d1fae5, text #065f46,
border #6ee7b7), outcome-warn (amber: bg #fef3c7, text #92400e, border #fcd34d),
outcome-fail (red: bg #fee2e2, text #991b1b, border #fca5a5). Use font-weight 700
(vs 600 for standard badges) to make the outcome badge visually distinguishable from
other status badges (AC7) and convey the completion result more prominently (AC8).
The distinct colors for each state enable immediate visual differentiation.
Files: langgraph_pipeline/web/templates/item.html

### D5: Update dynamic-refresh JS to handle outcome badge

Addresses: P1, UC1
Satisfies: AC1, AC4
Approach: In the selective-refresh JS block, add a handler for the "outcome" field
from the /dynamic JSON response. It updates the data-dynamic="outcome-badge" element
innerHTML with the appropriate badge markup when outcome is non-null, or clears it
when null. This keeps the badge current during auto-refresh polling.
Files: langgraph_pipeline/web/templates/item.html

---

## Design -> AC Traceability Grid

| AC | Design Decision(s) | Approach |
|---|---|---|
| AC1 | D1, D2, D3 | Outcome derived from completion record, passed to template/JSON, rendered as badge |
| AC2 | D1 | _derive_outcome retrieves outcome field from the completion record data |
| AC3 | D1 | Badge rendering logic renders the retrieved outcome as a visible badge element |
| AC4 | D2, D3, D5 | Outcome in template context + first-position badge + JS refresh = visible at a glance without navigation |
| AC5 | D3 | Badge inserted before all other badges (first child of item-badges div) |
| AC6 | D3, D4 | Badge displays exactly three values (success/warn/fail) with distinct CSS per value |
| AC7 | D4 | Font-weight 700, semantic colors, and border distinguish outcome from other badges (font-weight 600) |
| AC8 | D4 | Higher font-weight and colored background make outcome badge the dominant visual signal |
