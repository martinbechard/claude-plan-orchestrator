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

- langgraph_pipeline/web/routes/item.py -- add JSON endpoint, extract dynamic data computation
- langgraph_pipeline/web/templates/item.html -- remove meta refresh, add data-dynamic attributes, add JS refresh logic

### Data Flow

1. Page loads normally via GET /item/{slug} (full server-side render, no meta refresh tag)
2. JavaScript starts a 10-second setInterval timer (only when pipeline_stage is active)
3. Each tick fetches GET /item/{slug}/dynamic (JSON)
4. JS updates only the elements marked with data-dynamic attributes
5. When the endpoint returns a terminal pipeline_stage ("completed" or "unknown"), the timer stops

### Dynamic vs Static Boundary

Dynamic elements (updated each cycle):
- Pipeline stage badge and current task label
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
- Cross-reference validation reports
- Completion history table (only changes when a run finishes)
- Traces table
- Console output section
- Output artifacts section
- Breadcrumb, slug title, item type badge

## Design Decisions

### D1: Remove meta http-equiv refresh tag
- Addresses: P1, FR2
- Satisfies: AC9
- Approach: Delete the conditional meta refresh tag from the extra_head block in item.html
  (line 22-24). With this removed, the browser no longer performs full-page reloads. This is
  the root cause of all DOM state destruction -- removing it eliminates the problem at its
  source. The JS-based refresh mechanism (D4) takes over the responsibility of keeping
  dynamic data current.
- Files: langgraph_pipeline/web/templates/item.html

### D2: Add JSON endpoint for dynamic item data
- Addresses: FR1, FR2
- Satisfies: AC6, AC10
- Approach: Add a new GET /item/{slug}/dynamic endpoint to item.py that returns a JSON
  object containing only the values that change during processing: pipeline_stage,
  active_worker (dict or null), total_cost_usd, total_duration_s, total_tokens,
  avg_velocity, plan_tasks (list of {id, name, status, agent}), and validation_results
  (list of validation dicts). Reuse existing helper functions (_derive_pipeline_stage,
  _get_active_worker, _load_plan_tasks, _load_completions, _compute_total_tokens,
  _compute_avg_velocity, _load_validation_results) to compute these values. The endpoint
  mirrors the same dynamic computation as item_detail but returns JSON instead of rendering
  a template.
- Files: langgraph_pipeline/web/routes/item.py

### D3: Classify elements as dynamic/static with data attributes
- Addresses: FR3, FR1
- Satisfies: AC13, AC14, AC15
- Approach: Add data-dynamic="<name>" attributes to each dynamic element in the template.
  For example: data-dynamic="cost" on the cost value span, data-dynamic="tokens" on
  the token count span, data-dynamic="stage-badge" on the pipeline stage badge container,
  data-dynamic="worker-banner" on the active worker banner div, data-dynamic="plan-tasks"
  on the plan task list, data-dynamic="validation-results" on the validation results
  section. Static content sections have no data-dynamic attributes and are structurally
  excluded from updates. New dynamic elements can be added simply by adding a
  data-dynamic attribute and a corresponding update handler in the JS -- no changes to
  static sections needed.
- Files: langgraph_pipeline/web/templates/item.html

### D4: Implement JS fetch loop for selective DOM updates
- Addresses: FR2, FR1, UC1
- Satisfies: AC5, AC8, AC10, AC11
- Approach: Add a script block at the bottom of item.html that:
  (1) Reads the initial pipeline_stage from the server-rendered page.
  (2) If the stage is active (not "completed" or "unknown"), starts a setInterval
      timer at 10-second intervals.
  (3) Each tick calls fetch("/item/<slug>/dynamic") to get JSON.
  (4) For each field in the response, finds the corresponding data-dynamic element
      and updates its textContent or innerHTML.
  (5) Uses textContent for simple values (cost, tokens, duration, velocity) and
      innerHTML for complex rendered sections (badges, worker banner, plan tasks,
      validation results) that need structural HTML updates.
  (6) Stops the interval when pipeline_stage transitions to a terminal state.
  The fetch loop runs independently of user interaction with details/summary elements.
- Files: langgraph_pipeline/web/templates/item.html

### D5: Preserve details/summary state by never touching static containers
- Addresses: P1, P2, UC1
- Satisfies: AC1, AC2, AC3, AC4, AC12
- Approach: The JS update logic targets only specific data-dynamic elements and never
  replaces, removes, or re-renders their parent containers or sibling content sections.
  All details/summary elements (raw input, clause register, 5 whys, structured
  requirements, design, validation reports, verification evidence, console output previews)
  are outside the update boundary. Since the DOM nodes for static sections are never
  touched, their open/closed state, scroll position, and all interaction state is
  preserved across refresh cycles. No explicit state tracking or restoration is needed.
- Files: langgraph_pipeline/web/templates/item.html (architectural principle)

### D6: Stop refresh on terminal pipeline state
- Addresses: FR1
- Satisfies: AC8
- Approach: The JSON response includes pipeline_stage. After each fetch, the JS checks if
  the stage is "completed" or "unknown". If so, it calls clearInterval to stop the refresh
  timer. This mirrors the existing conditional meta refresh behavior (which only renders
  the tag when pipeline_stage is not completed/unknown). The timer also only starts when
  the initial server-rendered pipeline_stage indicates the item is still active.
- Files: langgraph_pipeline/web/templates/item.html

## Design -> AC Traceability Grid

| AC | Design Decision(s) | Approach |
|---|---|---|
| AC1 | D1, D4, D5 | Meta refresh removed; JS updates skip static sections; details elements untouched |
| AC2 | D1, D5 | No full-page reload; static containers including details never replaced |
| AC3 | D3, D5 | Only data-dynamic elements updated; static content cards have no such attributes |
| AC4 | D1, D5 | No page reload + static sections untouched = user can read indefinitely |
| AC5 | D4 | JS fetch loop runs on independent timer regardless of user interaction state |
| AC6 | D2, D3, D4 | JSON endpoint returns dynamic values; JS finds data-dynamic elements and updates them |
| AC7 | D3, D5 | Static sections have no data-dynamic attribute; never targeted by update logic |
| AC8 | D4, D6 | setInterval at 10s; stops on terminal state; matches original refresh cadence |
| AC9 | D1 | meta http-equiv refresh tag deleted from template extra_head block |
| AC10 | D2, D4 | New JSON endpoint + JS fetch call retrieves dynamic data each cycle |
| AC11 | D3, D4 | JS updates only elements with data-dynamic attributes; surrounding DOM untouched |
| AC12 | D5 | Details/summary elements are outside the update boundary; state preserved by design |
| AC13 | D3 | Static sections identified by absence of data-dynamic attribute; excluded from updates |
| AC14 | D3 | Dynamic elements explicitly enumerated via data-dynamic="cost", "tokens", etc. |
| AC15 | D3 | New dynamic elements added by data-dynamic attribute + JS handler; no static changes |
