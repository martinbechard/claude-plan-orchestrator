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

Addresses: P1, P2, UC1
Satisfies: AC2, AC3, AC6
Approach: Add a helper function _derive_outcome(completions) in item.py that returns
the outcome string from the most recent completion record (by finished_at), or None
if no completions exist. This reuses the existing _load_completions() data already
fetched in both item_detail() and item_dynamic(). The function returns Optional[str]
-- one of "success", "warn", "fail", or None.
Files: langgraph_pipeline/web/routes/item.py

### D2: Pass outcome to template context and dynamic JSON

Addresses: P2, UC1
Satisfies: AC3, AC4
Approach: In item_detail(), call _derive_outcome(completions) and add "outcome" to
the template context dict. In item_dynamic(), also call _derive_outcome(completions)
and include "outcome" in the JSON response. This ensures the badge renders on initial
page load and updates during auto-refresh.
Files: langgraph_pipeline/web/routes/item.py

### D3: Render outcome badge as first element in badge list

Addresses: FR1, UC1
Satisfies: AC1, AC4, AC5, AC7, AC8
Approach: In item.html, insert a new span before the item_type badge inside the
item-badges div. The badge uses data-dynamic="outcome-badge" for auto-refresh. It
renders only when outcome is not None. The badge text displays the outcome value
(success/warn/fail). Being the first child of item-badges makes it the leftmost
(most prominent) badge.
Files: langgraph_pipeline/web/templates/item.html

### D4: Add CSS styles for outcome badge variants

Addresses: FR1, UC1
Satisfies: AC7, AC8
Approach: Add three CSS classes: outcome-success (green), outcome-warn (amber),
outcome-fail (red). These use distinct, saturated colours to make the outcome the
primary visual indicator -- more prominent than the muted pipeline-stage badges.
Files: langgraph_pipeline/web/templates/item.html

### D5: Update dynamic-refresh JS to handle outcome badge

Addresses: P2, UC1
Satisfies: AC4, AC6
Approach: In the selective-refresh JS block, add a handler for the "outcome" field
from the /dynamic JSON response. It updates the data-dynamic="outcome-badge" element
innerHTML with the appropriate badge markup, or hides it when outcome is null.
Files: langgraph_pipeline/web/templates/item.html

---

## Design -> AC Traceability Grid

| AC | Design Decision(s) | Approach |
|---|---|---|
| AC1 | D3 | Outcome badge is the first child in item-badges div |
| AC2 | D1 | _derive_outcome reads outcome from completion record |
| AC3 | D1, D2 | Helper retrieves outcome; route passes to template/JSON |
| AC4 | D2, D3, D5 | Badge element rendered in template, updated by JS refresh |
| AC5 | D3 | Badge inserted before all other badges (first position) |
| AC6 | D1, D5 | Outcome visible at a glance; auto-refresh keeps it current |
| AC7 | D3, D4 | Saturated colour scheme makes outcome visually prominent |
| AC8 | D4 | CSS classes map to exactly success/warn/fail values |
