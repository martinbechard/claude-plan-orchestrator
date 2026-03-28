# Frontend Implementation Design: Traces Page Usability Overhaul

## Overview

This proposal details the Jinja2 template structure, CSS/styling architecture,
responsive layout, and JavaScript interactions for the traces page overhaul.
It covers both the list page (proxy_list.html) and the detail/narrative page
(proxy_narrative.html), addressing requirements P2, P8, P9, P15, UC2, UC3,
UC4, FR2 and design decisions D8, D9, D10.

The strategy is evolutionary: restructure the existing templates to support
richer data, better semantics, and progressive disclosure, while keeping the
CSS token footprint minimal and the JavaScript vanilla (no framework needed).

---

## 1. List Page Redesign (proxy_list.html)

### 1.1 Template Structure

The current flat table has 7 columns including a redundant "Item slug" column
(AC4). The redesign replaces this with a cleaner layout:

```
Page title: "Execution History" (already done - AC12)

Filter bar: [Name] [Trace ID] [Model dropdown] [Date from] [Date to] [Apply] [Clear]
  (No changes needed - existing filter bar works well)

Toolbar: [Group by item toggle]
  (Existing toggle is adequate)

Table columns (flat mode):
  Trace ID | Item | Type | Start Time | Duration | Cost | Model | Outcome

Table columns (grouped mode):
  [expand] | Item | Type | Last Run | Duration | Cost | Model | Outcome
```

**Key column changes:**

- **Remove**: The old "Item slug" column was identical to "Item" -- already
  removed in the current template.
- **Add "Type" column**: Shows a badge (defect/feature/analysis) derived from
  the item slug prefix or metadata. Uses existing CSS classes
  `.item-type-defect`, `.item-type-feature`, `.item-type-analysis` from
  style.css (lines 458-471).
- **Rename "Status" to "Outcome"**: Use outcome-badge styling (`.outcome-success`,
  `.outcome-warn`, `.outcome-fail`) for completed runs; keep the
  `.badge-running` for still-running/stale runs.

**Jinja2 macro for type badge:**

```
{% macro type_badge(slug) -%}
{%- set slug_lower = (slug or "") | lower -%}
{%- if slug_lower.startswith("bug-") or "defect" in slug_lower -%}
  <span class="item-type-badge item-type-defect">Defect</span>
{%- elif slug_lower.startswith("feat-") or "feature" in slug_lower -%}
  <span class="item-type-badge item-type-feature">Feature</span>
{%- else -%}
  <span class="item-type-badge item-type-unknown">Task</span>
{%- endif -%}
{%- endmacro %}
```

**Jinja2 macro for outcome badge:**

```
{% macro outcome_badge(status) -%}
{%- if status == "error" -%}
  <span class="outcome-badge outcome-fail" role="status">Failed</span>
{%- elif status == "completed" -%}
  <span class="outcome-badge outcome-success" role="status">Completed</span>
{%- elif status == "stale" -%}
  <span class="badge badge-unknown" role="status">Stale</span>
{%- else -%}
  <span class="badge badge-running" role="status">Running</span>
{%- endif -%}
{%- endmacro %}
```

**Route context addition**: The route handler needs to pass a `display_type`
field on each enriched run dict. This is derived from the slug:
- Slugs containing digit-dash prefix (e.g., "03-bug-title") and the word
  "bug"/"defect" -> "defect"
- Slugs containing "feat"/"feature" -> "feature"
- Otherwise -> "task"

This classification belongs in `_enrich_run()` in `routes/proxy.py` as a simple
string check -- no new query needed.

### 1.2 CSS Approach

The list page needs minimal new CSS. The existing style.css already contains:
- `.item-type-badge`, `.item-type-defect`, `.item-type-feature` (lines 458-471)
- `.outcome-badge`, `.outcome-success`, `.outcome-warn`, `.outcome-fail` (lines 474-487)
- `.badge-running` (in proxy_narrative.html, move to style.css)

**New CSS required** (add to proxy_list.html extra_head or style.css):

```css
/* Move badge-running from narrative to shared style.css */
.badge-running { background: #dbeafe; color: #1e40af; }

/* Type column sizing */
th.col-type, td.col-type { width: 80px; white-space: nowrap; }
```

That is the entirety of new CSS for the list page. All other styles exist.

### 1.3 Responsive Behavior

The list page table is wrapped in `.table-wrap` which uses `overflow: hidden`.
For responsive behavior on narrow screens:

```css
@media (max-width: 768px) {
  .table-wrap { overflow-x: auto; }
  .filter-bar { flex-direction: column; }
  .filter-bar label { min-width: 100%; }
  .filter-bar input, .filter-bar select { min-width: unset; width: 100%; }
}
```

This allows the filter bar to stack vertically on mobile while the table
scrolls horizontally. The existing `max-width: 1200px` on `<main>` handles
wide screens.

### 1.4 Flat Table Row Template

```html
<tr>
  <td class="trace-id" style="font-family:monospace;font-size:12px;white-space:nowrap;">
    <span title="{{ run.run_id }}">{{ run.run_id[:8] }}</span>
    <button type="button" class="copy-btn" aria-label="Copy trace ID"
            onclick="navigator.clipboard.writeText('{{ run.run_id }}')">&#128203;</button>
    {% if run.child_count %}
    <br><span style="font-size:10px;color:#9090b0;">{{ run.child_count }} spans</span>
    {% endif %}
  </td>

  <td class="name">
    <a href="/proxy/{{ run.run_id }}/narrative">
      {{ run.display_slug if run.display_slug else run.name }}
    </a>
  </td>

  <td class="col-type">{{ type_badge(run.display_slug or run.name) }}</td>

  <td>
    {% if run.start_time %}
      <time datetime="{{ run.start_time }}" class="local-time">
        {{ run.start_time[:10] }} {{ run.start_time[11:19] }}
      </time>
    {% else %}&mdash;{% endif %}
  </td>

  <td style="text-align:right;font-variant-numeric:tabular-nums;">
    {{ run.display_duration or "&mdash;" | safe }}
  </td>

  <td style="text-align:right;font-variant-numeric:tabular-nums;">
    {{ run.display_cost or "&mdash;" | safe }}
  </td>

  <td>{{ run.display_model or "&mdash;" | safe }}</td>

  <td>{{ outcome_badge(run.display_status) }}</td>
</tr>
```

---

## 2. Narrative Detail Page Redesign (proxy_narrative.html)

### 2.1 Template Structure

The detail page has four major sections. Each is restructured:

**A. Header Row**: Back link + action buttons

```
[<- Back to traces]  [View work item]  [Worker logs (N)]  [Show raw trace]
```

Changes:
- Keep existing "Back to traces" and "View work item" links
- Add worker log count badge
- Move "Show raw trace" from link-to-separate-page to inline toggle (FR2, AC41-44)

**B. Run Header Card**: Summary metadata

```
+------------------------------------------------------------------+
| {display_name}  [Completed badge]                                |
| Started: {datetime}  |  Duration: {total}  |  Cost: {total}     |
| Phases: {count}                                                  |
|                                                                  |
| [Design doc link] [Validation link] [Worker logs] [Git commits] |
+------------------------------------------------------------------+
```

Changes:
- Title already shows `display_name` (resolved correctly)
- Add artifact links section below the metadata (AC19, AC20, AC37-40)
- Worker logs section already exists; enhance to show as clickable links

**C. Phase Timeline**: Vertical timeline with expandable cards

```
01  Intake              12.34s  $0.0012  [Pass]
    > Click to expand: files read, files written, commands, agent activity

02  Planning            45.67s  $0.0345  [Pass]
    > Click to expand...

03  Execution           2m 15s  $0.1234  [Pass]
    > Click to expand...
```

Changes:
- Phase headers already have duration and cost (AC31, AC32)
- Phase expansion body already shows files read/written and bash commands (AC33-36)
- No structural changes needed -- the existing template handles this well
- Ensure the data layer provides correct durations (handled by D4)

**D. Raw Trace Toggle**: New inline section at bottom (FR2, AC41-44)

```
[Show raw trace] button -> reveals a collapsible JSON block
  with run metadata, inputs, outputs as formatted JSON
```

### 2.2 Artifact Links Section

The header card needs a new artifact links row. This comes from two sources:

1. **Route context**: The route handler queries for related artifacts:
   - Work item page: `/item/{slug}` (already linked in header)
   - Worker logs: already in `worker_logs` context variable
   - Design doc: from child run metadata `design_doc` field
   - Git commits: from child run metadata or git log for the slug

2. **Template structure** for the links section:

```html
<div class="artifact-links">
  {% if display_name %}
  <a href="/item/{{ display_name }}" class="artifact-link">
    <span class="artifact-link-icon">&#128196;</span> Work item
  </a>
  {% endif %}

  {% if view.design_doc %}
  <a href="{{ view.design_doc }}" class="artifact-link">
    <span class="artifact-link-icon">&#128209;</span> Design doc
  </a>
  {% endif %}

  {% if view.validation_report %}
  <a href="{{ view.validation_report }}" class="artifact-link">
    <span class="artifact-link-icon">&#9989;</span> Validation
  </a>
  {% endif %}

  {% if worker_logs %}
  <a href="#worker-logs" class="artifact-link"
     onclick="document.getElementById('worker-logs').scrollIntoView({behavior:'smooth'})">
    <span class="artifact-link-icon">&#128220;</span> Worker logs ({{ worker_logs | length }})
  </a>
  {% endif %}

  {% if view.git_commits %}
  <a href="#git-commits" class="artifact-link">
    <span class="artifact-link-icon">&#128200;</span> Git commits
  </a>
  {% endif %}
</div>
```

**CSS for artifact links:**

```css
.artifact-links {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  flex: 1 1 100%;
  margin-top: 0.5rem;
  padding-top: 0.5rem;
  border-top: 1px solid #e2e8f0;
}

.artifact-link {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  font-size: 12px;
  font-weight: 500;
  color: #3b6fcf;
  text-decoration: none;
  padding: 3px 10px;
  border: 1px solid #d0d5dd;
  border-radius: 4px;
  background: #fff;
  transition: background 0.15s;
}

.artifact-link:hover {
  background: #eff4ff;
  border-color: #3b6fcf;
  text-decoration: none;
}

.artifact-link-icon { font-size: 14px; }
```

### 2.3 Data Model Extension for Artifact Links

The `ExecutionView` dataclass needs two new optional fields:

```python
@dataclass
class ExecutionView:
    item_slug: str
    total_duration: str
    total_cost: str
    phases: list[PhaseView]
    overall_status: str = "unknown"
    design_doc: str = ""        # path from phase artifacts
    validation_report: str = "" # path from phase artifacts
    git_commits: list[str] = field(default_factory=list)
```

These are populated by scanning the phase artifacts that are already extracted
by `_extract_artifacts()` in `trace_narrative.py`. The function already
recognizes design docs (`docs/plans/`), plan YAMLs, work items, and log files.
We just need to promote the first matching design doc and validation report
to the view level for easy template access.

### 2.4 Raw Trace Toggle (FR2, AC41-44)

Replace the current "Show raw trace" link (which navigates to `/proxy/{run_id}`)
with an inline toggle that reveals JSON data without a page load.

**Template structure:**

```html
{# ── Raw trace section (hidden by default) ─────────────────── #}
<div id="raw-trace-section" style="display:none;" aria-hidden="true">
  <h2>Raw Trace Data</h2>

  <div class="json-block">
    <details>
      <summary>Run metadata</summary>
      <pre>{{ run.metadata_json | fromjson | tojson(indent=2) if run.metadata_json else "{}" }}</pre>
    </details>
  </div>

  <div class="json-block">
    <details>
      <summary>Run inputs</summary>
      <pre>{{ run.inputs_json | default("{}", true) }}</pre>
    </details>
  </div>

  <div class="json-block">
    <details>
      <summary>Run outputs</summary>
      <pre>{{ run.outputs_json | default("{}", true) }}</pre>
    </details>
  </div>
</div>
```

**Toggle button** (replaces the current `.raw-toggle` link in the header):

```html
<button type="button" class="raw-toggle" id="raw-trace-btn"
        onclick="toggleRawTrace()" aria-pressed="false"
        aria-controls="raw-trace-section">
  &#128270; Show raw trace
</button>
```

**JavaScript:**

```javascript
function toggleRawTrace() {
  var section = document.getElementById('raw-trace-section');
  var btn = document.getElementById('raw-trace-btn');
  var isHidden = section.style.display === 'none';
  section.style.display = isHidden ? 'block' : 'none';
  section.setAttribute('aria-hidden', isHidden ? 'false' : 'true');
  btn.setAttribute('aria-pressed', isHidden ? 'true' : 'false');
  btn.innerHTML = isHidden ? '&#128270; Hide raw trace' : '&#128270; Show raw trace';
}
```

This reuses the existing `.json-block` CSS from style.css (lines 298-337),
keeping the visual style consistent with other collapsible JSON blocks in the
application. The raw trace data is rendered server-side in the HTML (so no
additional API call needed) but visually hidden by `display:none`.

### 2.5 Phase Expansion Enhancements

The current phase expansion already shows files read, files written, and bash
commands. This section is already implemented well. Minor enhancements:

**Agent response summary**: Currently the phase body shows activity pills
("Read 5 files", "edited 2", etc.) which is a good summary. For AC36
("expanded view shows agent responses"), add a truncated agent response
excerpt if the grandchild run outputs contain assistant text content:

```html
{% if phase.agent_response %}
<div class="file-detail-group">
  <div class="file-detail-title">Agent response (excerpt)</div>
  <div class="agent-response-excerpt">{{ phase.agent_response[:500] }}
    {% if phase.agent_response | length > 500 %}...{% endif %}
  </div>
</div>
{% endif %}
```

```css
.agent-response-excerpt {
  font-size: 12px;
  color: #334155;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 4px;
  padding: 8px;
  max-height: 200px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-word;
}
```

The `agent_response` field would be added to `PhaseView` and populated from
the outputs_json of grandchild runs where content type is "text".

### 2.6 Worker Logs as Clickable Links (AC20, AC39)

Currently worker logs are displayed as plain text filenames. Change to
clickable file paths that either link to a log viewer endpoint or anchor
to a logs section:

```html
{% if worker_logs %}
<div class="worker-logs" id="worker-logs">
  <div class="worker-logs-title">Worker output logs</div>
  {% for log in worker_logs %}
  <div class="worker-log-entry">
    <a href="/logs/{{ log }}" target="_blank" rel="noopener"
       class="worker-log-link">logs/{{ log }}</a>
  </div>
  {% endfor %}
</div>
{% endif %}
```

If no `/logs/` endpoint exists yet, the logs can be served as static files
or the links can simply point to the filesystem path as informational text.
The key UX improvement is making them visually scannable with the link styling.

---

## 3. Responsive Layout Strategy

### 3.1 Breakpoint System

The application uses a single `max-width: 1200px` container. Add responsive
breakpoints:

```css
/* ── Responsive: Tablet ─────────────────────────────── */
@media (max-width: 768px) {
  /* Filter bar stacks vertically */
  .filter-bar { flex-direction: column; }
  .filter-bar label { min-width: 100%; }
  .filter-bar input, .filter-bar select { min-width: unset; width: 100%; }

  /* Table scrolls horizontally */
  .table-wrap { overflow-x: auto; -webkit-overflow-scrolling: touch; }

  /* Narrative header stacks */
  .narrative-header-row { flex-direction: column; align-items: flex-start; }

  /* Phase cards reduce padding */
  .phase-header { padding: 0.5rem 0.75rem 0.5rem 1rem; gap: 0.5rem; }
  .phase-meta { flex-wrap: wrap; gap: 0.5rem; }

  /* Artifact links wrap more aggressively */
  .artifact-links { gap: 0.35rem; }
  .artifact-link { font-size: 11px; padding: 2px 8px; }
}

/* ── Responsive: Mobile ─────────────────────────────── */
@media (max-width: 480px) {
  main { padding: 0 0.75rem; margin: 0.75rem auto; }
  h1 { font-size: 18px; }

  /* Phase number shrinks */
  .phase-number { font-size: 16px; min-width: 20px; }

  /* Timeline padding reduces */
  .narrative-timeline { padding-left: 28px; }
  .narrative-timeline::before { left: 10px; }
  .phase-dot { left: -22px; width: 10px; height: 10px; top: 14px; }
}
```

### 3.2 Print Styles

For users who want to print execution reports:

```css
@media print {
  nav { display: none; }
  .filter-bar, .list-toolbar, .raw-toggle, .copy-btn { display: none; }
  .phase-card { break-inside: avoid; }
  .phase-body { display: block !important; } /* expand all phases */
  .phase-card.open .phase-body { display: block; }
}
```

---

## 4. JavaScript Interactions

### 4.1 Existing Interactions (Unchanged)

1. **toggleGroup(btn)**: Expands/collapses grouped run rows in list page
2. **togglePhase(id)**: Expands/collapses phase cards in narrative page
3. **local-time conversion**: Converts UTC timestamps to local time on page load
4. **clipboard copy**: Copies trace ID on button click

### 4.2 New Interactions

**Raw trace toggle** (Section 2.4 above): Simple show/hide with ARIA updates.

**Expand all phases** shortcut: A convenience button to expand/collapse all
phase cards at once:

```html
<div class="list-toolbar" style="margin-bottom:0.5rem;">
  <button type="button" class="group-toggle-link" onclick="toggleAllPhases()"
          id="expand-all-btn">
    &#9776; Expand all phases
  </button>
</div>
```

```javascript
function toggleAllPhases() {
  var cards = document.querySelectorAll('.phase-card');
  var btn = document.getElementById('expand-all-btn');
  var anyOpen = false;
  for (var i = 0; i < cards.length; i++) {
    if (cards[i].classList.contains('open')) { anyOpen = true; break; }
  }
  for (var i = 0; i < cards.length; i++) {
    var header = cards[i].querySelector('.phase-header');
    if (anyOpen) {
      cards[i].classList.remove('open');
      header.setAttribute('aria-expanded', 'false');
    } else {
      cards[i].classList.add('open');
      header.setAttribute('aria-expanded', 'true');
    }
  }
  btn.innerHTML = anyOpen
    ? '&#9776; Expand all phases'
    : '&#9776; Collapse all phases';
}
```

No other new JavaScript is required. The application deliberately avoids
frameworks to keep the page lightweight (no build step, no bundle).

---

## 5. CSS Architecture Decisions

### 5.1 Style Organization

The current split is:
- `style.css`: Shared layout, nav, tables, badges, pagination
- `proxy_list.html <style>`: List-specific styles (copy-btn, group-toggle, etc.)
- `proxy_narrative.html <style>`: Narrative-specific styles (phases, timeline, etc.)

**Recommendation**: Keep this split. It follows the Jinja2 `{% block extra_head %}`
pattern cleanly. Inline styles in extra_head load only on the pages that need
them, reducing CSS parse time on other pages.

**Move to style.css**: The `.badge-running` class (currently only in narrative)
should move to shared `style.css` since it is now used on both pages.

### 5.2 Color System

The existing color tokens are well-defined:
- **Background**: `#f5f7fa` (page), `#fff` (cards/tables), `#f8fafc` (hover/secondary)
- **Text**: `#1a1a2e` (primary), `#374151` (secondary), `#6b7280` (muted), `#9090b0` (faint)
- **Accent**: `#3b6fcf` (links/buttons), `#2d5ab8` (hover)
- **Borders**: `#e2e8f0` (default), `#d0d5dd` (inputs), `#f0f0f0` (light dividers)

No new colors needed. All new elements use existing palette values.

### 5.3 Component Reuse

The following CSS components are already defined and should be reused:
- `.badge` + variants: for all status indicators
- `.item-type-badge` + variants: for type classification
- `.outcome-badge` + variants: for run outcomes
- `.json-block`: for raw trace JSON display
- `.detail-header` / `.detail-meta`: for the run header card
- `.filter-bar`: for the search/filter form

---

## 6. Accessibility Considerations

### 6.1 Existing ARIA (Preserved)

- `role="search"` on filter form
- `role="region"` on table wraps
- `role="status"` on badges
- `role="list"` / `role="listitem"` on timeline and pills
- `aria-expanded` on toggle buttons
- `aria-label` on all interactive elements

### 6.2 New ARIA

- `aria-pressed` on the raw trace toggle button (AC41-44)
- `aria-controls` linking the toggle button to the raw trace section
- `aria-hidden` on the raw trace section when collapsed
- `aria-label="Expand all phases"` on the expand-all button

### 6.3 Keyboard Navigation

All interactive elements are native `<button>` or `<a>` elements, so they
receive focus naturally. The expand/collapse interactions use `onclick` on
buttons which is keyboard-accessible. No custom key handlers needed.

---

## 7. Data Flow Summary

```
Route handler (proxy.py)
  |
  |-- _enrich_run() adds: display_slug, display_duration, display_cost,
  |                        display_model, display_status, display_type (new)
  |
  |-- build_execution_view() produces: ExecutionView with phases,
  |                                     design_doc, validation_report (new)
  |
  v
Jinja2 Template
  |
  |-- Macros: type_badge(), outcome_badge() (both use existing CSS classes)
  |-- Phase cards: already render files_read, files_written, bash_commands
  |-- Raw trace: inline JSON blocks with show/hide toggle
  |-- Artifact links: derived from ExecutionView fields
  |
  v
Browser (vanilla JS)
  |
  |-- togglePhase(): expand/collapse individual phase cards
  |-- toggleAllPhases(): expand/collapse all at once (new)
  |-- toggleRawTrace(): show/hide raw JSON section (new)
  |-- toggleGroup(): expand/collapse grouped runs (existing)
  |-- local-time: convert UTC to local timezone (existing)
```

---

## 8. Implementation Sequence

The frontend changes depend on data layer fixes (Sections 2-4 of the YAML plan)
being completed first. The implementation order within the frontend work:

1. **style.css**: Move `.badge-running` to shared CSS, add responsive media queries
2. **proxy_list.html**: Add type badge column, switch to outcome badges,
   update column headers
3. **routes/proxy.py**: Add `display_type` to `_enrich_run()`
4. **trace_narrative.py**: Add `design_doc`, `validation_report` fields to
   ExecutionView; add `agent_response` to PhaseView
5. **proxy_narrative.html**: Add artifact links section, raw trace toggle,
   expand-all button, agent response excerpt
6. **Responsive testing**: Verify at 480px, 768px, 1200px breakpoints

---

## 9. Acceptance Criteria Coverage

| AC | How Addressed |
|---|---|
| AC4 | Type badge column replaces redundant slug column |
| AC12 | Page title already "Execution History" (no change needed) |
| AC13 | Detail page title uses resolved display_name (already works) |
| AC19 | Artifact link to /item/{slug} in header card |
| AC20 | Worker logs shown as clickable links with count badge |
| AC24 | Each row displays item slug in "Item" column |
| AC25 | Each row displays type badge (defect/feature/task) |
| AC26 | Each row displays start time |
| AC27 | Duration column shows real child-aggregated duration |
| AC28 | Cost column shows real aggregated cost |
| AC29 | Each row displays outcome badge |
| AC30 | Row click navigates to narrative view (already works) |
| AC31 | Phase shows real elapsed duration (data layer fix) |
| AC32 | Phase shows real cost (data layer fix) |
| AC33 | Phase cards are expandable (already implemented) |
| AC34 | Expanded view shows files read (already implemented) |
| AC35 | Expanded view shows commands run (already implemented) |
| AC36 | Expanded view shows agent response (new excerpt field) |
| AC37 | Artifact link to design document |
| AC38 | Artifact link to validation results |
| AC39 | Artifact link to worker output logs |
| AC40 | Artifact link to git commits |
| AC41 | Raw trace toggle button present in header |
| AC42 | Raw trace hidden by default (display:none) |
| AC43 | Toggle reveals full raw JSON inline |
| AC44 | Toggle hides raw JSON when pressed again |

---

## 10. Risk Assessment

**Low risk**: All changes are evolutionary on existing working templates.
No new dependencies, no build step changes, no new API endpoints required
for the core functionality.

**Medium risk**: The `agent_response` extraction from grandchild outputs
may need tuning -- LLM response content can be deeply nested in the
outputs_json. A truncation limit of 500 chars prevents UI flooding.

**No risk**: The raw trace toggle is a pure frontend feature -- the JSON
data is already available in the template context (it was previously shown
as a separate page view).
