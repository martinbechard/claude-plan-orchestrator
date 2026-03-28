# Systems Design: Selective Refresh Mechanism

Source: tmp/plans/.claimed/72-item-page-auto-refresh-collapses-sections.md
Requirements: docs/plans/2026-03-28-72-item-page-auto-refresh-collapses-sections-requirements.md
Competition role: systems-designer (task 0.1)

## Problem Statement

The item detail page (item.html) uses a full-page meta http-equiv refresh that reloads
the entire DOM every 10 seconds, destroying all element state including details/summary
open/closed state. Users cannot read expanded content sections during processing.

## Architecture Overview

Replace the meta refresh with a two-part mechanism:

1. A new JSON endpoint (GET /item/{slug}/dynamic) that returns only the fields that
   change during processing
2. A client-side setInterval + fetch loop that reads the JSON and surgically updates
   only the DOM elements marked with data-dynamic attributes

The key architectural principle is the **dynamic/static boundary**: certain template
variables change during processing (cost, tokens, pipeline stage, worker info) while
others are fixed once the page loads (requirements HTML, original request, slug, item type).
The JSON endpoint returns only the dynamic subset, and the JS client only touches DOM
elements for those fields.

## JSON Endpoint Data Model

### Dynamic vs Static Field Classification

The item_detail route passes 16 context variables to the template. Classification:

| Field | Dynamic? | Rationale |
|---|---|---|
| pipeline_stage | YES | Changes as worker progresses (executing -> validating -> completed) |
| active_worker | YES | Appears/disappears as worker starts/stops; elapsed time ticks |
| total_cost_usd | YES | Increases as completions accumulate; overridden by live worker stats |
| total_duration_s | YES | Increases during processing; overridden by live worker elapsed time |
| total_tokens | YES | Increases as completions accumulate; overridden by live worker counts |
| avg_velocity | YES | Recalculated as new completions arrive; overridden by live worker velocity |
| plan_tasks | YES | Task statuses change from pending -> in_progress -> completed during execution |
| validation_results | YES | New validation JSON files appear during execution |
| slug | NO | URL parameter, never changes |
| item_type | NO | Derived from backlog directory, fixed for the item lifetime |
| requirements_html | NO | Rendered from markdown file, does not change during processing |
| original_request_html | NO | Rendered from backlog file, does not change during processing |
| completions | NO* | Grows over time but the completion history table is not a refresh target |
| traces | NO* | Grows over time but traces section is not a refresh target |
| output_files | NO* | Grows over time but console output section is not a refresh target |
| output_artifacts | NO* | Grows over time but artifacts section is not a refresh target |
| last_trace | NO | Derived from traces, used for header link only |

*These fields do change during processing, but the work item explicitly limits the dynamic
refresh scope to status/cost/duration/worker/tokens/velocity/plan tasks/validation results.
Refreshing these additional sections would add complexity without addressing the core
problem (section collapse). They can be added to the dynamic set in a future iteration.

### JSON Response Schema

The endpoint returns a flat JSON object. Field names match the template context variable
names to keep the mapping obvious.

```
GET /item/{slug}/dynamic
Content-Type: application/json

{
  "pipeline_stage": "executing",
  "active_worker": {
    "pid": 12345,
    "elapsed_s": "3m 42s",
    "elapsed_raw_s": 222.4,
    "run_id": "abc-def-123",
    "current_task": "#2.1 Implement login form",
    "current_velocity": 4200,
    "tokens_in": 150000,
    "tokens_out": 45000,
    "cost_usd": 0.0234
  },
  "total_cost_usd": 0.0234,
  "total_duration_s": 222.4,
  "total_tokens": 195000,
  "avg_velocity": 4200,
  "plan_tasks": [
    {"id": "1.1", "name": "Scaffold project", "status": "completed", "agent": "coder"},
    {"id": "2.1", "name": "Implement login form", "status": "in_progress", "agent": "frontend-coder"}
  ],
  "validation_results": [
    {
      "task_id": "1.1",
      "verdict": "PASS",
      "message": "All checks passed",
      "requirements_checked": 3,
      "requirements_met": 3
    }
  ]
}
```

When no worker is active, active_worker is null. When no plan exists, plan_tasks is null.
When no validation results exist, validation_results is an empty list.

### Type Contract (for documentation; Python returns dicts)

```
DynamicItemResponse:
  pipeline_stage: str       -- one of: executing, validating, completed, planning,
                               claimed, designing, queued, stuck, unknown
  active_worker: ActiveWorkerInfo | null
  total_cost_usd: float
  total_duration_s: float
  total_tokens: int
  avg_velocity: int | null
  plan_tasks: list[PlanTask] | null
  validation_results: list[ValidationResult]

ActiveWorkerInfo:
  pid: int
  elapsed_s: str            -- formatted "Xm Ys"
  elapsed_raw_s: float      -- raw seconds for client-side calculations
  run_id: str | null
  current_task: str | null  -- formatted "#ID Name"
  current_velocity: int
  tokens_in: int
  tokens_out: int
  cost_usd: float

PlanTask:
  id: str
  name: str
  status: str               -- one of: pending, in_progress, completed, skipped, failed
  agent: str | null

ValidationResult:
  task_id: str
  verdict: str              -- one of: PASS, WARN, FAIL
  message: str
  requirements_checked: int | null
  requirements_met: int | null
```

## API Boundary Design

### Endpoint Specification

```
GET /item/{slug}/dynamic

Parameters:
  slug (path): Work item slug (e.g. "01-some-feature")

Response:
  200: DynamicItemResponse (JSON)
  404: Not applicable -- mirrors item_detail behavior of never returning 404

Content-Type: application/json
Cache-Control: no-cache, no-store
```

The endpoint is added to the existing item router (APIRouter) in item.py alongside the
existing GET /item/{slug}, GET /item/{slug}/output/{filename}, and
GET /item/{slug}/artifact-content endpoints.

### Why a Separate Endpoint (Not a Query Parameter)

Alternative considered: GET /item/{slug}?format=json

Rejected because:
- Conflates the HTML page endpoint with the JSON API, making it harder to add
  middleware (caching, rate limiting) to just one
- The JSON response deliberately omits static fields; using the same URL suggests the
  full resource representation
- Clean REST semantics: /item/{slug} is the HTML representation, /item/{slug}/dynamic
  is the JSON sub-resource for its mutable state

### No Authentication Required

The existing item_detail endpoint has no authentication. The dynamic endpoint mirrors
this -- it is a read-only view of the same data that the HTML page already renders.

## Data Flow: Existing Helpers to JSON Response

The new endpoint reuses the same helper functions as item_detail. The computation is a
strict subset -- only the 8 dynamic fields are computed, not the 16 total fields.

### Call Graph

```
item_dynamic(slug)
  |
  +-- _load_completions(slug)         --> completions (list[dict])
  |     Used internally for deriving pipeline_stage, cost, duration, tokens, velocity
  |
  +-- _derive_pipeline_stage(slug, completions)  --> pipeline_stage (str)
  |     Checks: active workers -> completed dirs -> claimed -> plan/design -> backlog
  |
  +-- _get_active_worker(slug)        --> active_worker (dict | None)
  |     Reads DashboardState.active_workers, computes elapsed time, finds current task
  |     Internally calls _load_plan_tasks(slug) to find in_progress task
  |
  +-- _load_plan_tasks(slug)          --> plan_tasks (list[dict] | None)
  |     Loads YAML plan file, flattens sections into task list
  |
  +-- _load_validation_results(slug)  --> validation_results (list[dict])
  |     Reads validation-*.json files from worker-output directory
  |
  +-- _compute_total_tokens(completions)   --> total_tokens (int)
  |     Estimates: sum(tpm * duration_s / 60) across completions
  |
  +-- _compute_avg_velocity(completions)   --> avg_velocity (int | None)
  |     Averages tokens_per_minute across completions with values
  |
  +-- (inline) sum cost_usd from completions --> total_cost_usd (float)
  +-- (inline) sum duration_s from completions --> total_duration_s (float)
  +-- (inline) live stats override when active_worker is present
```

### Shared Logic Extraction

The item_detail and item_dynamic endpoints share the computation of the 8 dynamic fields
including the active_worker live-stats override. To avoid duplication:

Extract a private helper function:

```
_compute_dynamic_fields(slug) -> dict
```

This function encapsulates:
1. Load completions
2. Derive pipeline_stage
3. Get active_worker
4. Load plan_tasks
5. Load validation_results
6. Compute total_cost_usd, total_duration_s, total_tokens, avg_velocity from completions
7. Apply active_worker live-stats override

Both endpoints call this function. item_detail additionally loads the static fields
(requirements_html, original_request_html, item_type, etc.) and passes everything to
the template. item_dynamic returns the dict directly as JSONResponse.

This keeps the two endpoints in sync: any change to how dynamic fields are computed
is reflected in both the initial page render and the periodic refresh.

### Live Stats Override Logic

When active_worker is not None, certain completion-derived stats are replaced with
live values from the worker (mirroring lines 110-117 of the current item_detail):

```
if active_worker:
    if active_worker.tokens_in + active_worker.tokens_out > 0:
        total_tokens = active_worker.tokens_in + active_worker.tokens_out
    if active_worker.cost_usd > 0:
        total_cost_usd = active_worker.cost_usd
    total_duration_s = active_worker.elapsed_raw_s
    if active_worker.current_velocity > 0:
        avg_velocity = active_worker.current_velocity
```

This override is part of _compute_dynamic_fields so it applies identically to both
the initial page render and the JSON refresh.

## Client-Side Consumption

### Fetch Loop Lifecycle

```
Page load (server-rendered HTML)
  |
  +-- Check initial pipeline_stage (server-rendered into a data attribute or JS variable)
  |
  +-- If stage is terminal ("completed" or "unknown"): do not start timer
  |
  +-- Else: start setInterval(refreshDynamic, 10000)
        |
        +-- Each tick:
        |     fetch("/item/{slug}/dynamic")
        |       .then(response => response.json())
        |       .then(data => {
        |           updateDynamicElements(data)
        |           if (data.pipeline_stage === "completed" ||
        |               data.pipeline_stage === "unknown") {
        |               clearInterval(timerId)
        |           }
        |       })
        |       .catch(err => {
        |           // Network error: skip this cycle, retry next tick
        |           console.warn("Refresh failed:", err)
        |       })
```

### Data Attribute Mapping

Each dynamic DOM element has a data-dynamic attribute whose value names the JSON field
it displays. The JS updateDynamicElements function iterates over a mapping:

| data-dynamic value | JSON field path | Update strategy |
|---|---|---|
| "pipeline-stage" | pipeline_stage | Replace badge text + CSS class |
| "cost" | total_cost_usd | Replace textContent with formatted value |
| "tokens" | total_tokens | Replace textContent with formatted value |
| "duration" | total_duration_s | Replace textContent with formatted value |
| "velocity" | avg_velocity | Replace textContent + show/hide element |
| "velocity-badge" | avg_velocity | Replace badge text + show/hide |
| "worker-banner" | active_worker | Show/hide entire banner + update contents |
| "plan-tasks" | plan_tasks | Replace innerHTML of task list container |
| "plan-tasks-count" | plan_tasks | Replace completion count text |
| "validation-results" | validation_results | Replace innerHTML of validation container |

### Formatting Responsibility

The JSON endpoint returns raw numeric values. The JS client is responsible for
formatting them for display:

- Cost: toFixed(4) with "$" prefix
- Duration: convert seconds to "Xh Ym" / "Xm Ys" / "Xs" format
- Tokens: toLocaleString() for thousand separators
- Velocity: format as "X.Xk tok/min" or "X tok/min"

This keeps the API clean (raw data) and allows the client to match the exact formatting
currently produced by Jinja2 filters.

### Plan Tasks HTML Reconstruction

The plan_tasks update replaces the innerHTML of the task list UL element. The JS builds
the same HTML structure that the Jinja2 template currently produces:

```
<li class="task-item">
  <span class="task-icon task-icon--{status}" title="{status}">
    {icon based on status}
  </span>
  <span class="task-name {task-name--done if completed}">
    {task.name}
  </span>
  <span class="task-id-label">#{task.id}</span>
</li>
```

The completion count header ("X / Y") is updated separately via the plan-tasks-count
data-dynamic element.

### Validation Results HTML Reconstruction

Similarly, the validation results update replaces the innerHTML of the validation
container. Each result maps to:

```
<div class="validation-row">
  <span class="badge {verdict-class}">{verdict}</span>
  <strong>Task {task_id}</strong>
  <span class="validation-criteria">{met}/{checked} criteria met</span>
  <p class="validation-message">{message}</p>
</div>
```

### Worker Banner Update Strategy

The active_worker field is either an object or null. The update logic:

- If null: hide the banner div (display: none)
- If object: show the banner div, update its child spans with pid, elapsed_s,
  current_task, run_id (for trace link)

The banner is always present in the DOM (rendered hidden by default when no worker),
so the JS just toggles visibility and updates content. This avoids innerHTML replacement
on the banner, preserving any ARIA live region semantics.

### Status Badge Update Strategy

The pipeline_stage badge requires both text and CSS class updates:

1. Remove all status-* classes from the badge element
2. Add status-{pipeline_stage} class
3. Update textContent to the stage name (or active_worker.current_task if applicable)

The conditional logic mirrors the Jinja2 template:
- If active_worker exists and has current_task: show current_task as badge text
- If active_worker exists but no current_task and stage is executing/validating:
  show "intake / planning"
- Otherwise: show pipeline_stage

## Error Handling and Graceful Degradation

### Fetch Failure

If the fetch fails (network error, server error), the JS simply logs a warning and
waits for the next interval tick. The page remains functional with its last-known data.
No retry backoff is needed because the interval already provides regular retries.

### Endpoint Returns 500

The JS catch block handles this identically to network errors. The page displays
stale-but-valid data until the next successful fetch.

### JavaScript Disabled

If JavaScript is disabled, the page renders normally via the initial server-side render
but never refreshes. This is acceptable because:
- The meta refresh is being removed, so there is no refresh mechanism at all without JS
- The primary use case (monitoring processing progress) requires JS for a good UX
- Users who need the latest data can manually reload the page

## Performance Considerations

### Endpoint Cost

The _compute_dynamic_fields function calls 5 helper functions that each perform I/O:
- _load_completions: DB query (proxy SQLite)
- _derive_pipeline_stage: checks filesystem (completed dirs, claimed dir, plan YAML)
- _get_active_worker: reads in-memory DashboardState + loads plan YAML (if worker active)
- _load_plan_tasks: reads plan YAML
- _load_validation_results: reads validation JSON files

Total I/O per call: 1 DB query + ~5-10 filesystem stat/reads. This is identical to the
current full-page refresh cost (the same helpers are called). The JSON response is much
smaller (~1-2 KB vs ~50-100 KB HTML page), so network transfer is reduced.

### Request Frequency

10-second interval matches the existing meta refresh interval. One client viewing one
item generates 6 requests/minute. With the dashboard typically open on 1-2 items at a
time, this is negligible load.

### No Caching

The endpoint sets Cache-Control: no-cache, no-store because the data can change between
any two requests (worker status, elapsed time, task progress). Browser caching would
defeat the purpose of the refresh.

## Design -> AC Traceability

| AC | How This Design Addresses It |
|---|---|
| AC1 | No full-page reload (meta refresh removed); JS updates only data-dynamic elements, never touching details/summary containers |
| AC2 | JSON endpoint provides all dynamic values; JS updates status/cost/duration/tokens elements each cycle |
| AC3 | Static content sections have no data-dynamic attributes and are never modified by JS |
| AC4 | endpoint returns pipeline_stage; JS checks for terminal state and clearInterval; timer starts only for active items |
| AC5 | meta http-equiv refresh tag deleted from template extra_head block |
| AC6 | setInterval + fetch replaces meta refresh; JSON endpoint + DOM updates provide the same information |
| AC7 | Only data-dynamic elements updated; DOM structure of static sections never touched |
| AC8 | No full-page reload means browser never resets details/summary state; JS never modifies details elements |
