# Plan Orchestrator — UI Style Guide

<!-- docs/ui-style-guide.md
     Canonical style reference for the Plan Orchestrator web UI.
     Design: docs/plans/2026-03-26-37-ui-quality-process-lost-in-langgraph-migration-design.md -->

This document is the single source of truth for visual conventions in the Plan
Orchestrator web UI. Read it before making any change to a file under
`langgraph_pipeline/web/`. All values below are extracted directly from
`langgraph_pipeline/web/static/style.css`.

---

## Colour Palette

### Brand / Structural

| Token | Hex | Usage |
|-------|-----|-------|
| `--navy` | `#1a1a2e` | Nav background, body text, worker slug |
| `--bg-page` | `#f5f7fa` | Page background (`body`) |
| `--bg-surface` | `#ffffff` | Cards, tables, filter bars |
| `--bg-subtle` | `#f8fafc` | Table header, row-detail background, JSON block header |
| `--border` | `#e2e8f0` | All card / table borders |
| `--border-light` | `#f0f0f0` | Table row dividers |
| `--border-input` | `#d0d5dd` | Form inputs, pagination buttons |

### Text

| Token | Hex | Usage |
|-------|-----|-------|
| `--text-primary` | `#1a1a2e` | Body, headings |
| `--text-secondary` | `#374151` | Table headers, timeline labels |
| `--text-muted` | `#6b7280` | Worker body, meta details |
| `--text-faint` | `#9090b0` | Nav links (idle), axis ticks |
| `--text-nav-active` | `#e8e8f0` | Nav brand, hovered nav links |
| `--text-nav-link` | `#9090b0` | Nav links (idle state) |

### Interactive

| Token | Hex | Usage |
|-------|-----|-------|
| `--blue` | `#3b6fcf` | Links, primary buttons, filter button, focus ring |
| `--blue-hover` | `#2d5ab8` | Filter button hover |
| `--blue-light` | `#eff4ff` | Pagination / toggle hover background |
| `--nav-active-bg` | `rgba(126,184,247,0.22)` | Active nav link background pill |
| `--nav-active-ring` | `rgba(126,184,247,0.3)` | Active nav link box-shadow ring |
| `--nav-active-text` | `#e8e8f0` | Active nav link text |
| `--nav-hover-bg` | `rgba(255,255,255,0.07)` | Idle nav link hover background |

### Status / Outcome Badges

| Class | Background | Text | Meaning |
|-------|-----------|------|---------|
| `.badge-success` / `.outcome-success` | `#d1fae5` | `#065f46` | Passed / completed |
| `.badge-error` / `.outcome-fail` | `#fee2e2` | `#991b1b` | Error / failed |
| `.outcome-warn` | `#fef3c7` | `#92400e` | Warning |
| `.badge-unknown` | `#f3f4f6` | `#6b7280` | Unknown / neutral |

### Item-Type Badges

| Class | Background | Text |
|-------|-----------|------|
| `.item-type-defect` | `#fee2e2` | `#991b1b` |
| `.item-type-feature` | `#dbeafe` | `#1e40af` |
| `.item-type-analysis` | `#ede9fe` | `#6d28d9` |
| `.item-type-unknown` | `#f3f4f6` | `#6b7280` |

### System Status

| Token | Hex | Usage |
|-------|-----|-------|
| `--green-live` | `#10b981` | Live connection dot, live timeline bar |
| `--red-dead` | `#ef4444` | Dead connection, error count badge, error rows |
| `--amber` | `#f59e0b` | Warn border on timeline completion bars |

---

## Typography

The UI uses the system font stack throughout — no web fonts are loaded.

```
font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif
```

### Scale

| Element | Size | Weight | Notes |
|---------|------|--------|-------|
| Body | 14px | 400 | `line-height: 1.5` |
| `h1` | 20px | 600 | `margin: 0 0 1rem` |
| `h2` | 16px | 600 | `margin: 1.5rem 0 0.75rem` |
| Nav brand | 15px | 600 | `letter-spacing: 0.02em` |
| Nav links | 13px | 400 | |
| Table body | 13px | 400 | |
| Table headers (`th`) | 13px | 600 | Uppercase is NOT used on table headers |
| Filter inputs | 13px | 400 | |
| Filter labels | 12px | 500 | |
| Badges | 11px | 600 | `text-transform: uppercase; letter-spacing: 0.04em` |
| Status/meta text | 12px | 400 | `.detail-meta`, `.worker-card-body` |
| Session stat value | 20px | 700 | `line-height: 1.2` |
| Session stat label | 11px | 500 | `text-transform: uppercase; letter-spacing: 0.06em` |
| Code / pre blocks | 11–12px | 400 | Monospace via `pre` defaults |

---

## Spacing

The baseline unit is `0.25rem` (4px). Common multiples:

| Value | Pixels | Usage |
|-------|--------|-------|
| `0.25rem` | 4px | Badge padding (vertical), small gaps |
| `0.5rem` | 8px | Icon margin, small gaps |
| `0.75rem` | 12px | Card padding, filter bar padding, section gaps |
| `1rem` | 16px | `h1` bottom margin, card/gantt padding |
| `1.25rem` | 20px | Detail header horizontal padding |
| `1.5rem` | 24px | Nav horizontal padding, `main` margin, large section gaps |

### Table cell padding

All `th` and `td` use `padding: 8px 12px`. Do not override individual cells with
different padding values — use this uniform rule across every table in the UI.

### Card / surface layout

Standard card pattern — white background, `#e2e8f0` border, `6px` radius:

```css
background: #fff;
border: 1px solid #e2e8f0;
border-radius: 6px;
```

Inner padding for content cards: `padding: 1rem 1.25rem` (detail-header style) or
`padding: 0.75rem 1rem` (worker cards, timeline container).

---

## Layout

```css
main {
    max-width: 1200px;
    margin: 1.5rem auto;
    padding: 0 1.5rem;
}
```

The `main` content area is centred at 1200px max-width with 1.5rem side padding.
Do not add nested wrappers that re-center content inside `main`.

---

## Navigation

The nav bar is `48px` tall with `#1a1a2e` background and `1.5rem` horizontal padding.

### Active state

Apply class `active` to the current page's `<a>` tag. The active nav link uses:

```css
color: #e8e8f0;
background: rgba(126, 184, 247, 0.22);
box-shadow: 0 0 0 1px rgba(126, 184, 247, 0.3);
font-weight: 500;
```

This creates a clearly visible pill with a subtle ring outline. All nav links
share `padding: 0.25rem 0.625rem` and `border-radius: 4px` to prevent layout
shift on navigation. Idle links use `color: #9090b0` and no background. Hover
adds `background: rgba(255,255,255,0.07)` and changes color to `#e8e8f0`.

---

## Tables

All tables follow a single shared pattern via `style.css`. Do not add inline styles
or per-page overrides.

### Structure

```html
<div class="table-wrap">
  <table>
    <thead>
      <tr><th>Column</th> ...</tr>
    </thead>
    <tbody>
      <tr><td class="name"><a href="...">Slug</a></td> ...</tr>
    </tbody>
  </table>
</div>
```

### Column alignment rules

- **Text columns** (names, slugs, descriptions): `text-align: left` (default).
- **Numeric columns** (cost, tokens, counts, durations): `text-align: right`.
- **Status / badge columns**: `text-align: left` (badges are inline-block).

Apply right-alignment via an inline `style="text-align:right"` on both the `th`
and every `td` in that column, or via a scoped CSS class if the pattern repeats.

### Header style

`thead th` has `background: #f8fafc`, `border-bottom: 1px solid #e2e8f0`,
`font-weight: 600`, `color: #374151`. Headers are NOT uppercase.

### Row hover

`tbody tr:hover > td` gets `background: #fafbff`. This is handled by `style.css`
automatically — no per-template rule needed.

### Cost values

Display plain `$0.0123` — no tilde prefix. The tilde convention was removed because
it looks like a bug to users. Scan templates for `~$` and replace with `$`.

---

## Pagination Component

The `.pagination` element sits below the table and above the next section.

### HTML pattern

```html
<div class="pagination">
  {% if page > 1 %}
    <a href="?page={{ page - 1 }}{{ qs }}">&laquo; Prev</a>
  {% else %}
    <span class="disabled">&laquo; Prev</span>
  {% endif %}

  <span class="pagination-page-info">Page {{ page }} of {{ total_pages }}</span>

  {% if page < total_pages %}
    <a href="?page={{ page + 1 }}{{ qs }}">Next &raquo;</a>
  {% else %}
    <span class="disabled">Next &raquo;</span>
  {% endif %}
</div>
```

### CSS rules (from `style.css`)

```css
.pagination {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 0.75rem 0 0.75rem 2px;   /* left-flush with table content */
    font-size: 13px;
    color: #555;
}
.pagination-page-info { font-size: 14px; font-weight: 500; color: #333; }
.pagination a { padding: 4px 12px; border: 1px solid #d0d5dd; border-radius: 4px; color: #3b6fcf; background: #fff; }
.pagination a:hover { background: #f0f5ff; text-decoration: none; }
.pagination .disabled { padding: 4px 12px; border: 1px solid #e5e7eb; border-radius: 4px; color: #c0c0c0; background: #fafafa; cursor: default; }
```

The left padding (`padding-left: 2px`) keeps the pagination flush with the left
edge of the table. Do not remove it.

---

## Empty States

Use the `.empty-state` pattern whenever a list or table has zero rows.

### HTML pattern

```html
<div class="empty-state">
  <div class="icon">&#128203;</div>
  <div><strong>No items found</strong></div>
  <div>Sub-text explaining why or what to do next.</div>
</div>
```

### Required elements

1. **Icon** — emoji in a `<div class="icon">` (32px, `margin-bottom: 0.5rem`).
2. **Heading** — short bold label describing the empty state.
3. **Sub-text** — one sentence explaining the state or next action.

### CSS

```css
.empty-state { text-align: center; padding: 3rem 1rem; color: #888; font-size: 14px; }
.empty-state .icon { font-size: 32px; margin-bottom: 0.5rem; }
```

Do not omit the icon or the sub-text. An empty state with only a heading is not
sufficient — users need context.

### Page-specific empty states

| Page | Icon | Heading | Sub-text |
|------|------|---------|----------|
| Dashboard (workers) | `&#128736;` | No active workers | All workers are idle. |
| Queue | `&#128203;` | Queue is empty | No items are waiting for processing. |
| Completions | `&#9989;` | No completions yet | Completed runs will appear here. |
| Traces | `&#128270;` | No traces | Proxy traces will appear here once requests are made. |

---

## Card Layouts

### Surface card (generic)

Used for filter bars, table wrappers, gantt charts, JSON blocks, and detail headers.

```css
background: #fff;
border: 1px solid #e2e8f0;
border-radius: 6px;
```

### Detail header card (`.detail-header`)

Used on the item detail page to show run metadata at a glance.

```css
.detail-header {
    padding: 1rem 1.25rem;
    margin-bottom: 1rem;
    display: flex;
    flex-wrap: wrap;
    gap: 1.5rem;
    align-items: center;
}
.detail-header .run-name { font-size: 16px; font-weight: 600; flex: 1 1 100%; }
.detail-meta { font-size: 12px; color: #555; }
.detail-meta span { display: block; font-size: 13px; font-weight: 500; color: #1a1a2e; }
```

Each metadata field is a `.detail-meta` block containing a label text node and a
`<span>` for the value.

### Worker card (`.worker-card`)

Used on the dashboard to show active workers in a responsive grid.

```css
.worker-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 0.75rem; }
.worker-card { background: #fff; border: 1px solid #e2e8f0; border-radius: 6px; padding: 0.75rem 1rem; display: flex; flex-direction: column; gap: 0.5rem; }
```

### Session summary bar (`.session-summary`)

Dark banner (`#1a1a2e`) that bleeds to the edges of `main`, showing aggregate stats.

```css
.session-summary { background: #1a1a2e; color: #e8e8f0; padding: 0.75rem 1.5rem; margin: -1.5rem -1.5rem 1.5rem; }
```

Stats use `.session-stat-value` (20px/700) over `.session-stat-label` (11px/500,
uppercase, `#9090b0`).

---

## Status Badges

All badges share the same base structure regardless of variant:

```css
.badge {
    display: inline-block;
    padding: 1px 8px;
    border-radius: 10px;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}
```

Use `.badge-success`, `.badge-error`, or `.badge-unknown` for run/verification
status. Use `.item-type-*` for work item type. Use `.outcome-*` for completion
outcomes. Do not invent new badge variants — extend the existing set if needed.

---

## Expandable Details

Row-level details use the native `<details>` / `<summary>` element styled via
`.row-details`. The summary triangle is rendered via `::before` pseudo-element
(`▶` / `▼`); suppress the native marker with `list-style: none`.

JSON collapsible blocks use `.json-block > details`, which adds a header band
(`#f8fafc` background, 10px/14px padding) that opens to reveal a scrollable `pre`.

---

## Do Not

- Add inline `style="..."` for colours, font sizes, or spacing that are already
  covered by `style.css` classes. Use the class instead.
- Use `~$` for cost values. Always display `$0.0123`.
- Leave empty states as plain text (`<p>No items.</p>`). Always use the
  `.empty-state` icon + heading + sub-text pattern.
- Override `th` / `td` padding per-template. Use the global `8px 12px` rule.
- Skip the active class on nav links. Every page must set `class="active"` on its
  own nav entry.
- Add new font sizes outside the scale table above without updating this guide.
