# Design: 72 Item Page Auto-Refresh Collapses Sections

Source: tmp/plans/.claimed/72-item-page-auto-refresh-collapses-sections.md
Requirements: docs/plans/2026-03-28-72-item-page-auto-refresh-collapses-sections-requirements.md

## Architecture Overview

The item detail page (item.html) uses a full-page meta http-equiv refresh that reloads the
entire DOM every 10 seconds. This destroys all element state, including details/summary
open/closed state, making it impossible to read expanded sections during processing.

The fix replaces the meta refresh with a JavaScript setInterval + fetch pattern that
retrieves only dynamic data from a new JSON endpoint and surgically updates specific
DOM elements. Static content sections are never touched, preserving all DOM state.

### Key Files

- langgraph_pipeline/web/routes/item.py -- add JSON endpoint, refactor dynamic data extraction
- langgraph_pipeline/web/templates/item.html -- remove meta refresh, add data-dynamic IDs, add JS refresh logic

### Data Flow

1. Page loads normally via GET /item/{slug} (full server-side render, no meta refresh tag)
2. JavaScript starts a 10-second setInterval timer
3. Each tick fetches GET /item/{slug}/dynamic (JSON)
4. JS updates only the elements marked with data-dynamic-* attributes
5. When the endpoint returns a terminal pipeline_stage ("completed" or "unknown"), the timer stops

### Dynamic vs Static Boundary

Dynamic elements (updated each cycle):
- Pipeline stage badge
- Active worker banner (presence, PID, task, elapsed time, trace link)
- Cost value
- Token count
- Duration value
- Velocity value and badge
- Plan task statuses and completion count
- Validation results (new results may appear during execution)

Static elements (never touched by refresh):
- Raw input card
- Clause register card
- 5 Whys analysis card
- Structured requirements card
- Design document card
- Validation reports (cross-reference)
- Breadcrumb, slug title, item type badge

## Design Decisions

### D1: Remove meta http-equiv refresh tag
- Addresses: P1, FR2
- Satisfies: AC1, AC5, AC8
- Approach: Delete the conditional meta refresh tag from the extra_head block in item.html.
  The tag is on line 23: meta http-equiv="refresh" content="10". With this removed, the browser
  no longer performs full-page reloads, so all DOM state (including details/summary open/closed)
  is preserved indefinitely.
- Files: langgraph_pipeline/web/templates/item.html

### D2: Add JSON endpoint for dynamic item data
- Addresses: FR1, FR2
- Satisfies: AC2, AC4, AC6
- Approach: Add a new GET /item/{slug}/dynamic endpoint to item.py that returns a JSON object
  containing only the values that change during processing: pipeline_stage, active_worker dict,
  total_cost_usd, total_duration_s, total_tokens, avg_velocity, plan_tasks list, and
  validation_results list. Reuse existing helper functions (_derive_pipeline_stage,
  _get_active_worker, _load_plan_tasks, etc.) to compute these values. The endpoint mirrors the
  same computation as the main item_detail route but returns JSON instead of rendering a template.
- Files: langgraph_pipeline/web/routes/item.py

### D3: Mark dynamic elements with data attributes and update via JS
- Addresses: FR1, FR2
- Satisfies: AC2, AC3, AC6, AC7
- Approach: Add data-dynamic attribute IDs to the dynamic elements in the template (e.g.
  data-dynamic="cost", data-dynamic="tokens", data-dynamic="duration"). Add a script block
  at the bottom of item.html with a setInterval that fetches /item/{slug}/dynamic every 10
  seconds and updates the textContent/innerHTML of only those marked elements. Static content
  sections have no data-dynamic attributes and are never touched by the update logic.
- Files: langgraph_pipeline/web/templates/item.html

### D4: Preserve details/summary open/closed state by design
- Addresses: P1, FR2
- Satisfies: AC1, AC7, AC8
- Approach: Since the JS update logic only modifies the textContent of specific data-dynamic
  elements and never replaces or re-renders parent containers, all details/summary elements
  retain their current open/closed state across refresh cycles. No explicit state tracking or
  restoration is needed -- the DOM simply is not disturbed.
- Files: langgraph_pipeline/web/templates/item.html

### D5: Stop refresh when item reaches terminal state
- Addresses: FR1
- Satisfies: AC4
- Approach: The JSON response includes pipeline_stage. After each fetch, the JS checks if the
  stage is "completed" or "unknown". If so, it calls clearInterval to stop the refresh timer.
  This mirrors the existing conditional meta refresh behavior (which only renders the tag when
  pipeline_stage is not completed/unknown). Also starts the timer only when the initial
  server-rendered pipeline_stage indicates the item is still active.
- Files: langgraph_pipeline/web/templates/item.html

## Design -> AC Traceability Grid

| AC | Design Decision(s) | Approach |
|---|---|---|
| AC1 | D1, D4 | Remove meta refresh so no full-page reload; JS updates never touch details elements |
| AC2 | D2, D3 | JSON endpoint provides dynamic values; JS updates status/cost/duration/tokens elements |
| AC3 | D3 | JS only updates data-dynamic elements; static content cards have no such attributes |
| AC4 | D2, D5 | Endpoint returns pipeline_stage; JS clears interval on terminal state, runs while active |
| AC5 | D1 | Meta http-equiv refresh tag removed from template extra_head block |
| AC6 | D2, D3 | New JSON endpoint + JS fetch/setInterval replaces full-page reload mechanism |
| AC7 | D3, D4 | Only data-dynamic elements updated; rest of DOM including details containers untouched |
| AC8 | D1, D4 | No full-page reload means browser never resets details/summary open/closed state |
