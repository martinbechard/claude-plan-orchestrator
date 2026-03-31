# Design: 84 Item Page Missing Outcome Badge

Source: tmp/plans/.claimed/84-item-page-missing-outcome-badge.md
Requirements: docs/plans/2026-03-31-84-item-page-missing-outcome-badge-requirements.md

## Overview

The work item detail page shows status badges (item type, pipeline stage, velocity)
but does not display the completion outcome (success/warn/fail). The outcome data
already exists in the completions table via proxy.list_completions_by_slug() -- the
gap is purely in the rendering pipeline. This design adds an outcome badge as the
first element in the badge list, with corresponding CSS and dynamic-refresh support.

## Key Files

- langgraph_pipeline/web/routes/item.py -- add outcome derivation, pass to template and dynamic JSON
- langgraph_pipeline/web/templates/item.html -- render outcome badge and CSS styles
- tests/langgraph/web/test_item_outcome_badge.py -- unit tests for outcome derivation

## Design Decisions

### D1: Derive overall outcome from latest completion record

Addresses: P1, UC1
Satisfies: AC1, AC2, AC6
Approach: Add a helper function _derive_outcome(completions) in item.py that returns
the outcome string from the most recent completion record (by finished_at), or None
if no completions exist. This reuses the existing _load_completions() data already
fetched in both item_detail() and item_dynamic(). The function returns Optional[str]
-- one of "success", "warn", "fail", or None. It handles all three values (AC6) and
gracefully returns None when no completion record exists (AC7).
Files: langgraph_pipeline/web/routes/item.py

### D2: Pass outcome to template context and dynamic JSON

Addresses: P1, UC1
Satisfies: AC1, AC3, AC4
Approach: In item_detail(), call _derive_outcome(completions) and add "outcome" to
the template context dict. In item_dynamic(), also call _derive_outcome(completions)
and include "outcome" in the JSON response. This ensures the badge renders on initial
page load and updates during auto-refresh.
Files: langgraph_pipeline/web/routes/item.py

### D3: Render outcome badge as first element in badge list

Addresses: FR1, UC1
Satisfies: AC1, AC3, AC4, AC5, AC7
Approach: In item.html, insert a new span before the item_type badge inside the
item-badges div. The badge uses data-dynamic="outcome-badge" wrapper. Render only
when outcome is not None -- when no completion record exists, the badge element is
empty (AC7). The badge text displays the outcome value (success/warn/fail). Being
the first child of item-badges makes it the leftmost (most prominent) badge,
satisfying AC4 (visible without scrolling past other status) and AC5 (first position).
Files: langgraph_pipeline/web/templates/item.html

### D4: Add CSS styles for outcome badge variants

Addresses: FR1, UC1
Satisfies: AC4, AC6
Approach: Add three CSS classes: outcome-success (green: bg #d1fae5, text #065f46,
border #6ee7b7), outcome-warn (amber: bg #fef3c7, text #92400e, border #fcd34d),
outcome-fail (red: bg #fee2e2, text #991b1b, border #fca5a5). Use font-weight 700
to make these more prominent than other badges. Each class maps to one of the three
outcome values, ensuring all render distinctly (AC6).
Files: langgraph_pipeline/web/templates/item.html

### D5: Update dynamic-refresh JS to handle outcome badge

Addresses: P1, UC1
Satisfies: AC1, AC3, AC7
Approach: In the selective-refresh JS block, add a handler for the "outcome" field
from the /dynamic JSON response. It updates the data-dynamic="outcome-badge" element
innerHTML with the appropriate badge markup when outcome is non-null, or clears it
when null (AC7 -- gracefully absent during in-progress).
Files: langgraph_pipeline/web/templates/item.html

---

## Design -> AC Traceability Grid

| AC | Design Decision(s) | Approach |
|---|---|---|
| AC1 | D1, D2, D3, D5 | Outcome derived from completion record, passed to template/JSON, rendered as badge, kept current via dynamic refresh |
| AC2 | D1 | _derive_outcome retrieves outcome from the completion record data |
| AC3 | D2, D3, D5 | Outcome in template context + first-position badge + JS refresh = visible at a glance |
| AC4 | D2, D3, D4 | Badge appears first in badge list with prominent styling, no scrolling needed |
| AC5 | D3 | Badge inserted before all other badges (first child of item-badges div) |
| AC6 | D1, D4 | _derive_outcome returns success/warn/fail; CSS classes style each distinctly |
| AC7 | D1, D3, D5 | Returns None when no completions; badge element empty; JS clears on null |
