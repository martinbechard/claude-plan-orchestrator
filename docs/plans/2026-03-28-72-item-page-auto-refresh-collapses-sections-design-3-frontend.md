# Frontend Implementation Design: Selective Refresh Mechanism

Source: tmp/plans/.claimed/72-item-page-auto-refresh-collapses-sections.md
Design overview: docs/plans/2026-03-28-72-item-page-auto-refresh-collapses-sections-design.md
Competition entry: Task 0.3 (frontend-coder)

## Design Summary

Replace the full-page meta http-equiv refresh with a setTimeout-chained fetch loop that
retrieves JSON from a new endpoint and surgically updates only data-dynamic-marked DOM
elements. Static content sections (requirements, original request, artifacts, traces,
completions) are never touched, preserving all details/summary open/closed state.

---

## 1. Timer Strategy: setTimeout Chaining (not setInterval)

### Decision

Use recursive setTimeout instead of setInterval.

### Rationale

setInterval fires every N ms regardless of whether the previous fetch has completed. If
the server is slow or the network hiccups, requests pile up and responses arrive
out-of-order, causing stale data to overwrite fresh data. setTimeout chaining guarantees
that the next fetch starts only after the current one finishes (success or failure),
preventing request pileup and ensuring responses are always applied in order.

### Implementation Pattern

```
const REFRESH_INTERVAL_MS = 10000;
const MAX_BACKOFF_MS = 60000;
const BACKOFF_MULTIPLIER = 2;

var refreshTimer = null;
var currentDelay = REFRESH_INTERVAL_MS;

function scheduleRefresh() {
    refreshTimer = setTimeout(doRefresh, currentDelay);
}

function doRefresh() {
    fetch(dynamicUrl)
        .then(function (r) {
            if (!r.ok) throw new Error('HTTP ' + r.status);
            return r.json();
        })
        .then(function (data) {
            currentDelay = REFRESH_INTERVAL_MS;  // reset on success
            applyUpdate(data);
            if (!isTerminalStage(data.pipeline_stage)) {
                scheduleRefresh();
            }
        })
        .catch(function () {
            // Exponential backoff on error, capped at MAX_BACKOFF_MS
            currentDelay = Math.min(currentDelay * BACKOFF_MULTIPLIER, MAX_BACKOFF_MS);
            scheduleRefresh();
        });
}
```

### Lifecycle

- **Start condition**: The timer starts only when the server-rendered pipeline_stage is
  not "completed" and not "unknown". This is checked via a data attribute on the script
  container: data-initial-stage="{{ pipeline_stage }}".
- **Stop condition**: After each fetch, if pipeline_stage is "completed" or "unknown",
  clearTimeout(refreshTimer) and do not schedule another cycle.
- **Page visibility**: When the tab is hidden (document.hidden === true), skip the fetch
  and reschedule. This saves bandwidth when the user switches away. Resume immediately
  when the tab becomes visible via a visibilitychange listener.

---

## 2. Fetch Error Handling

### Strategy: Exponential Backoff with Silent Recovery

Errors should not disrupt the user experience. The page already shows the last known
good state from the initial server render, so a failed refresh is invisible to the user
except for briefly stale data.

### Error scenarios and responses

| Scenario | Response |
|---|---|
| Network error (fetch rejects) | Backoff: double the delay (10s -> 20s -> 40s -> 60s cap). Reschedule. |
| HTTP 404 (item deleted?) | Stop refreshing entirely. The item no longer exists. |
| HTTP 500 (server error) | Backoff same as network error. Server may recover. |
| JSON parse error | Backoff. Treat as transient server issue. |
| Successful response | Reset delay to REFRESH_INTERVAL_MS (10s). Apply update. |

### No error UI

Do not show error banners or toast notifications for refresh failures. The user is
reading static content; a subtle stale-data state is far less disruptive than an error
popup that interrupts reading. The backoff mechanism ensures recovery without user action.

---

## 3. DOM Update Strategy

### Principle: Surgical textContent Updates, Never innerHTML for User Content

The core update mechanism uses data-dynamic attributes to locate elements and updates
their textContent (for plain values) or specific attributes/classes (for badges and
visibility). innerHTML is only used for server-pre-rendered HTML fragments (plan tasks,
validation results) where the content structure changes between refreshes.

### 3.1 Simple Value Updates (textContent)

Elements displaying a single formatted value get a data-dynamic attribute:

```
<span class="item-cost-value" data-dynamic="cost">${{ "%.4f"|format(total_cost_usd) }}</span>
<span class="item-cost-value" data-dynamic="tokens">{{ "{:,}".format(total_tokens) }}</span>
<span class="item-cost-value" data-dynamic="duration">...</span>
<span class="item-cost-value" data-dynamic="velocity">...</span>
```

The JS update function sets textContent directly:

```
function updateText(key, value) {
    var el = document.querySelector('[data-dynamic="' + key + '"]');
    if (el) el.textContent = value;
}
```

The JSON endpoint returns pre-formatted display strings for these values so the JS
does not need to replicate Jinja formatting logic (comma-separated thousands, h/m/s
duration, k-abbreviated velocity). This keeps rendering logic on the server and avoids
duplication.

### JSON Response Shape (Display-Ready Values)

```
{
    "pipeline_stage": "executing",
    "active_worker": {
        "pid": 12345,
        "elapsed_s": "3m 42s",
        "run_id": "abc-123",
        "current_task": "#1.1 Add JSON endpoint",
        "current_velocity": 1250
    } | null,
    "cost_display": "$0.0847",
    "tokens_display": "142,350",
    "duration_display": "3m 42s",
    "velocity_display": "1.3k",
    "velocity_raw": 1250,
    "plan_tasks_html": "<ul class=\"task-list\">...</ul>",
    "plan_count_display": "3 / 8",
    "validation_results_html": "<div>...</div>" | null,
    "stage_badge_html": "<span class=\"badge status-executing\">#1.1 Add JSON endpoint</span>"
}
```

### 3.2 Complex Section Updates (innerHTML for Server-Rendered Fragments)

Three sections have complex conditional rendering that would be expensive to replicate
in client-side JS:

1. **Pipeline stage badge** - Has 3 conditional branches (active_worker with task,
   active_worker without task, no active_worker). The server renders the correct badge
   HTML and the client replaces the container innerHTML.

2. **Plan tasks list** - Task icons, classes, and completion count change. The server
   returns the full rendered task list. The client replaces the task list container.

3. **Validation results** - New results can appear during execution. The server returns
   the full rendered validation section.

For these, the JSON response includes pre-rendered HTML fragments. The client swaps
them into designated containers:

```
<div data-dynamic-html="stage-badge">
    <!-- server-rendered badge(s) here -->
</div>

<div data-dynamic-html="plan-tasks">
    <!-- server-rendered task list here -->
</div>

<div data-dynamic-html="validation-results">
    <!-- server-rendered validation results here -->
</div>
```

The applyUpdate function:

```
function updateHtml(key, html) {
    var el = document.querySelector('[data-dynamic-html="' + key + '"]');
    if (el && html !== undefined) el.innerHTML = html;
}
```

### 3.3 Active Worker Banner (Show/Hide Pattern)

The active worker banner is conditionally rendered by Jinja. On refresh, the worker may
start or stop. Instead of reconstructing the banner DOM in JS, use this pattern:

**Template change**: Always render the banner container, but add a hidden attribute when
no worker is active:

```
<div class="active-worker-banner" data-dynamic-html="worker-banner"
     role="status" aria-live="polite"
     {% if not active_worker %}hidden{% endif %}>
    <!-- banner content -->
</div>
```

**JS update**: The JSON response includes worker_banner_html (the full inner HTML of
the banner) or null when no worker is active:

```
function updateWorkerBanner(data) {
    var banner = document.querySelector('[data-dynamic-html="worker-banner"]');
    if (!banner) return;
    if (data.worker_banner_html) {
        banner.innerHTML = data.worker_banner_html;
        banner.hidden = false;
    } else {
        banner.hidden = true;
    }
}
```

This approach:
- Avoids creating/destroying DOM nodes (just show/hide)
- Keeps all HTML rendering in Jinja (server-side)
- Handles the worker appearing mid-refresh or disappearing naturally

### 3.4 Velocity Badge in Badges Area

The velocity badge in the header badges area may appear or disappear. Use the same
show/hide pattern:

```
<span class="badge velocity-badge" data-dynamic="velocity-badge"
      {% if not (avg_velocity is not none and avg_velocity > 0) %}hidden{% endif %}>
    {{ vel_label }}
</span>
```

JS updates textContent and toggles hidden based on velocity_raw from the response.

---

## 4. Data Attribute Naming Convention

### Naming Scheme

Two attribute families distinguish update strategies:

| Attribute | Update Method | Purpose |
|---|---|---|
| data-dynamic="name" | el.textContent = value | Simple text value replacement |
| data-dynamic-html="name" | el.innerHTML = html | Server-rendered HTML fragment swap |

### Complete Attribute Map

| Attribute | Element | JSON Field | Update |
|---|---|---|---|
| data-dynamic="cost" | .item-cost-value (Cost stat) | cost_display | textContent |
| data-dynamic="tokens" | .item-cost-value (Tokens stat) | tokens_display | textContent |
| data-dynamic="duration" | .item-cost-value (Duration stat) | duration_display | textContent |
| data-dynamic="velocity" | .item-cost-value (Velocity stat) | velocity_display | textContent (includes unit span) |
| data-dynamic="velocity-badge" | .badge.velocity-badge | velocity_raw | textContent + hidden toggle |
| data-dynamic-html="stage-badge" | wrapper around badge spans | stage_badge_html | innerHTML |
| data-dynamic-html="worker-banner" | .active-worker-banner | worker_banner_html | innerHTML + hidden toggle |
| data-dynamic-html="plan-tasks" | wrapper around task list | plan_tasks_html | innerHTML |
| data-dynamic="plan-count" | .item-card-count in Plan Tasks | plan_count_display | textContent |
| data-dynamic-html="validation-results" | wrapper around validation rows | validation_results_html | innerHTML |

### Why Two Attribute Families

Using a single data-dynamic for everything would require the JS to guess whether to use
textContent or innerHTML. Separate attributes make the update strategy explicit in the
markup, self-documenting, and impossible to accidentally inject HTML where only text is
expected (XSS defense).

---

## 5. HTML Template Changes

### 5.1 Remove Meta Refresh (D1)

Delete lines 21-23 from item.html:

```
{% if pipeline_stage != "completed" and pipeline_stage != "unknown" %}
<meta http-equiv="refresh" content="10">
{% endif %}
```

### 5.2 Add data-dynamic Attributes to Existing Elements

**Cost value** (current line 929):
```
Before: <span class="item-cost-value">${{ "%.4f"|format(total_cost_usd) }}</span>
After:  <span class="item-cost-value" data-dynamic="cost">${{ "%.4f"|format(total_cost_usd) }}</span>
```

**Tokens value** (current line 933):
```
Before: <span class="item-cost-value">{{ "{:,}".format(total_tokens) }}</span>
After:  <span class="item-cost-value" data-dynamic="tokens">{{ "{:,}".format(total_tokens) }}</span>
```

**Duration value** (current line 937):
```
Before: <span class="item-cost-value">...duration formatting...</span>
After:  <span class="item-cost-value" data-dynamic="duration">...duration formatting...</span>
```

**Velocity value** (current line 949):
```
Before: <span class="item-cost-value">...velocity formatting...</span>
After:  <span class="item-cost-value" data-dynamic="velocity">...velocity formatting...</span>
```

### 5.3 Wrap Complex Sections in data-dynamic-html Containers

**Stage badge** (wrap the existing badge conditionals):
```
<div data-dynamic-html="stage-badge" style="display:contents">
    {% if active_worker %}
      ... existing badge conditionals ...
    {% else %}
      ... existing badge ...
    {% endif %}
</div>
```

Using display:contents ensures the wrapper div does not affect the flex layout of
.item-badges.

**Plan tasks** (wrap the task list and empty state):
```
<div data-dynamic-html="plan-tasks">
    {% if plan_tasks %}
      <ul class="task-list">...</ul>
    {% else %}
      <div class="empty-state">...</div>
    {% endif %}
</div>
```

**Plan count** (add data-dynamic):
```
<span class="item-card-count" data-dynamic="plan-count">
    {{ completed_count }} / {{ total_count }}
</span>
```

**Validation results** (wrap the validation card body):
```
<div data-dynamic-html="validation-results">
    {% for vr in validation_results %}
      ... existing validation rows ...
    {% endfor %}
</div>
```

**Worker banner** (modify existing conditional):
```
Before: {% if active_worker %}<div class="active-worker-banner">...</div>{% endif %}
After:  <div class="active-worker-banner" data-dynamic-html="worker-banner"
              {% if not active_worker %}hidden{% endif %}>
            {% if active_worker %}...banner content...{% endif %}
        </div>
```

### 5.4 Add Refresh Script Block

Add after the existing artifact-viewer script block, before the closing endblock:

```
<script>
(function () {
    var REFRESH_INTERVAL_MS = 10000;
    var MAX_BACKOFF_MS = 60000;
    var BACKOFF_MULTIPLIER = 2;
    var TERMINAL_STAGES = ['completed', 'unknown'];

    var slug = {{ slug | tojson }};
    var dynamicUrl = '/item/' + encodeURIComponent(slug) + '/dynamic';
    var initialStage = {{ pipeline_stage | tojson }};

    // Do not start refresh if already in terminal state
    if (TERMINAL_STAGES.indexOf(initialStage) !== -1) return;

    var refreshTimer = null;
    var currentDelay = REFRESH_INTERVAL_MS;

    function updateText(key, value) {
        var el = document.querySelector('[data-dynamic="' + key + '"]');
        if (el && value !== undefined && value !== null) el.textContent = value;
    }

    function updateHtml(key, html) {
        var el = document.querySelector('[data-dynamic-html="' + key + '"]');
        if (el && html !== undefined) el.innerHTML = html;
    }

    function applyUpdate(data) {
        updateText('cost', data.cost_display);
        updateText('tokens', data.tokens_display);
        updateText('duration', data.duration_display);
        updateText('velocity', data.velocity_display);

        // Velocity badge: show/hide + update text
        var velBadge = document.querySelector('[data-dynamic="velocity-badge"]');
        if (velBadge) {
            if (data.velocity_raw && data.velocity_raw > 0) {
                velBadge.textContent = data.velocity_display + ' tok/min';
                velBadge.hidden = false;
            } else {
                velBadge.hidden = true;
            }
        }

        // Server-rendered HTML fragments
        updateHtml('stage-badge', data.stage_badge_html);
        updateHtml('plan-tasks', data.plan_tasks_html);
        updateText('plan-count', data.plan_count_display);

        // Worker banner: show/hide
        var banner = document.querySelector('[data-dynamic-html="worker-banner"]');
        if (banner) {
            if (data.worker_banner_html) {
                banner.innerHTML = data.worker_banner_html;
                banner.hidden = false;
            } else {
                banner.hidden = true;
            }
        }

        // Validation results (entire card body)
        if (data.validation_results_html !== undefined) {
            updateHtml('validation-results', data.validation_results_html);
        }
    }

    function isTerminal(stage) {
        return TERMINAL_STAGES.indexOf(stage) !== -1;
    }

    function scheduleRefresh() {
        refreshTimer = setTimeout(doRefresh, currentDelay);
    }

    function doRefresh() {
        if (document.hidden) {
            scheduleRefresh();
            return;
        }
        fetch(dynamicUrl)
            .then(function (r) {
                if (r.status === 404) throw { fatal: true };
                if (!r.ok) throw new Error('HTTP ' + r.status);
                return r.json();
            })
            .then(function (data) {
                currentDelay = REFRESH_INTERVAL_MS;
                applyUpdate(data);
                if (!isTerminal(data.pipeline_stage)) {
                    scheduleRefresh();
                }
            })
            .catch(function (err) {
                if (err && err.fatal) return; // stop on 404
                currentDelay = Math.min(
                    currentDelay * BACKOFF_MULTIPLIER, MAX_BACKOFF_MS
                );
                scheduleRefresh();
            });
    }

    // Resume immediately when tab becomes visible
    document.addEventListener('visibilitychange', function () {
        if (!document.hidden && refreshTimer) {
            clearTimeout(refreshTimer);
            doRefresh();
        }
    });

    scheduleRefresh();
}());
</script>
```

---

## 6. Server-Side JSON Endpoint

### Endpoint: GET /item/{slug}/dynamic

Returns a JSON object with both raw values (for logic) and display-formatted strings
(for DOM updates). Also includes pre-rendered HTML fragments for complex sections.

### Implementation Approach

The endpoint reuses the same helper functions as item_detail():
- _derive_pipeline_stage()
- _get_active_worker()
- _load_plan_tasks()
- _load_validation_results()
- _compute_total_tokens()
- _compute_avg_velocity()

For HTML fragments, use Jinja2's render_block or render a small sub-template. The
simplest approach: define small Jinja2 macro files or use environment.from_string()
to render fragments. Alternatively, render the full template and extract sections
(wasteful), or use template.module to render individual blocks.

Recommended approach: Create small Jinja2 template strings for each fragment (plan
tasks, stage badge, worker banner, validation results). These are simple enough to
define as Python string constants rendered via templates.env.from_string(). This avoids
creating separate template files for tiny fragments.

### Response Format

```
{
    "pipeline_stage": "executing",
    "active_worker": { ... } | null,
    "cost_display": "$0.0847",
    "tokens_display": "142,350",
    "duration_display": "3m 42s",
    "velocity_display": "1.3k",
    "velocity_raw": 1250,
    "stage_badge_html": "<span class=\"badge status-executing\">#1.1 Add endpoint</span>",
    "worker_banner_html": "<span class=\"active-worker-label\">...</span>...",
    "plan_tasks_html": "<ul class=\"task-list\">...</ul>",
    "plan_count_display": "3 / 8",
    "validation_results_html": "<div class=\"validation-row\">...</div>"
}
```

### Formatting Functions

Add helper functions to item.py for display formatting:

```
def _format_cost_display(cost_usd: float) -> str:
    return f"${cost_usd:.4f}"

def _format_tokens_display(tokens: int) -> str:
    return f"{tokens:,}"

def _format_duration_display(seconds: float) -> str:
    if seconds >= 3600:
        return f"{int(seconds // 3600)}h {int((seconds % 3600) // 60)}m"
    elif seconds >= 60:
        return f"{int(seconds // 60)}m {int(seconds % 60)}s"
    return f"{int(seconds)}s"

def _format_velocity_display(velocity: float | None) -> str:
    if velocity is None or velocity <= 0:
        return "\u2014"  # em-dash
    if velocity >= 1000:
        return f"{velocity / 1000:.1f}k"
    return str(int(velocity))
```

These mirror the Jinja formatting logic exactly, ensuring the initial server render
and subsequent JS updates show identical values.

---

## 7. Acceptance Criteria Traceability

| AC | How This Design Addresses It |
|---|---|
| AC1 | Meta refresh removed (Section 5.1). JS never touches details/summary elements. Static sections have no data-dynamic attributes. |
| AC2 | JS updates cost, tokens, duration, velocity, stage badge via data-dynamic attributes (Section 3.1, 3.2). |
| AC3 | Only elements with data-dynamic or data-dynamic-html attributes are modified. Requirements, original request, traces, completions, artifacts have no such attributes. |
| AC4 | JS checks pipeline_stage in each response. Terminal stages ("completed", "unknown") cause clearTimeout (Section 1). Timer only starts when initial stage is active (Section 1). |
| AC5 | Meta http-equiv refresh tag deleted from extra_head block (Section 5.1). |
| AC6 | New GET /item/{slug}/dynamic endpoint returns JSON (Section 6). setInterval replaced with setTimeout chain (Section 1). |
| AC7 | data-dynamic attributes on specific elements (Section 4). Static content has no attributes. details/summary elements untouched. |
| AC8 | No full-page reload. DOM structure preserved. details/summary open state maintained by not touching those elements. |

---

## 8. Risk Analysis and Mitigations

### Risk: HTML fragment injection (XSS)

The server-rendered HTML fragments (plan_tasks_html, worker_banner_html, etc.) use
innerHTML. This is safe because:
1. The content is rendered by Jinja2 on the same server, not from user input
2. Jinja2 auto-escapes all template variables by default
3. The fetch URL is hardcoded to the same origin (no CORS risk)

### Risk: Race condition on rapid tab switching

The visibilitychange handler calls doRefresh() immediately. If the user rapidly
switches tabs, multiple fetches could be in flight. Mitigation: Add an inFlight boolean
flag that prevents a new fetch while one is pending.

### Risk: Memory leak from orphaned timers

If the page is navigated away from (SPA-style), the timer continues. Mitigation: Not
applicable here since this is a traditional server-rendered page. Navigation causes a
full page unload which destroys all JS state.

### Risk: Stale HTML fragments after template changes

If the item.html template is updated but the fragment rendering in the JSON endpoint
is not synchronized, the page may show inconsistent styles. Mitigation: The fragment
rendering should use Jinja2 macros or include files shared between the full template
and the JSON endpoint, ensuring a single source of truth for markup.
