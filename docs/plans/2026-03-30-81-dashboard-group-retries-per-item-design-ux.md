# UX Design: Retry Grouping and Expandable History

Source item: tmp/plans/.claimed/81-dashboard-group-retries-per-item.md
Architecture design: docs/plans/2026-03-30-81-dashboard-group-retries-per-item-design.md

## Design Overview

This UX design covers the visual and interaction patterns for grouping retried
pipeline items in the dashboard completions table. The goal is to eliminate the
"duplicate row" confusion when an item retries (e.g. warn then success) by
presenting a single grouped row with expandable retry history.

The design builds on the existing dashboard patterns: light-themed table with
pill-shaped badges (11px, uppercase, rounded), 8px/12px cell padding, and
hover highlighting at #fafbff.

---

## D3: Retry Count Badge

### Decision: Compact "x2" pill badge after the outcome badge

**Placement**: The retry count badge appears immediately after the outcome badge
in the same Outcome table cell, separated by 6px horizontal gap. The outcome
badge always comes first because the final status is the primary information.

**Label format**: "x2", "x3", etc. -- where the number is the total attempt count
(including the final successful attempt).

**Why "x2" over alternatives**:

| Format | Pros | Cons |
|---|---|---|
| x2 | Compact, scannable, familiar (gaming/UI pattern) | Slightly ambiguous -- could mean "times 2" |
| 2 attempts | Unambiguous | Verbose for a table cell, breaks visual rhythm |
| (2) | Compact | Looks like a footnote, easily missed |
| retry: 1 | Clear about retry count | Too wordy, and confusing: is "1" the retry or total? |

The "x2" format wins because: (a) it fits the badge-width budget without wrapping,
(b) it is visually parallel to notification count badges, and (c) the context
(appearing next to an outcome badge on a row with a disclosure triangle) makes the
meaning unambiguous.

**Styling**:

```
.retry-count-badge {
  display: inline-block;
  padding: 1px 6px;
  border-radius: 10px;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.04em;
  background: #e2e8f0;    /* neutral slate-200 */
  color: #475569;          /* slate-600 */
  margin-left: 6px;
  vertical-align: middle;
}
```

The badge intentionally uses a neutral gray palette (not green/yellow/red) so it
does not compete with the outcome badge for attention. It is 1px smaller in font
size (10px vs 11px) and has slightly tighter padding to create a visual subordination.

**Visibility rule**: The retry count badge is only rendered when `attempt_count > 1`.
Items with a single attempt show no badge -- the absence of the badge is the signal
that no retries occurred.

---

## D4: Expandable Row Interaction Pattern

### Decision: Disclosure triangle prefix with row-level click target

**Toggle affordance**: A disclosure triangle character (Unicode &#x25B6; / &#x25BC;)
prepended to the item slug text in the first (Item) cell. Collapsed state shows a
right-pointing triangle; expanded state shows a downward-pointing triangle.

**Why disclosure triangle over chevron (>) or icon button**:

| Affordance | Pros | Cons |
|---|---|---|
| Disclosure triangle (&#x25B6;/&#x25BC;) | Native OS disclosure pattern, requires no icon library, lightweight | Less stylized |
| Chevron icon (&#x203A;) | Familiar from accordions | Needs CSS rotation, can feel heavier than needed |
| Expand button (+/-) | Very explicit | Too heavy for table rows, implies add/remove semantics |

The disclosure triangle is the standard pattern for hierarchical data in tables
(file explorers, tree views, macOS list views). It communicates expandability
without visual weight.

**Click target**: The entire first cell (Item cell) is the click target, not just the
triangle. This provides a large hit area (~200px wide) that is easy to click.
The cursor changes to `pointer` when hovering the Item cell of a retried row.

**Why the full cell, not just the triangle**:
- A 10px triangle is too small for comfortable clicking (Fitts's law)
- Users naturally click the item name when they want more details
- The item name link (`/item/{slug}`) can still be reached via the anchor element
  inside the cell -- clicking the link navigates, clicking the surrounding cell
  padding toggles expand

**Animation**: CSS transition on the triangle character via a wrapping span:

```
.retry-toggle {
  display: inline-block;
  transition: transform 0.15s ease;
  margin-right: 6px;
  font-size: 10px;
  color: #94a3b8;          /* slate-400, subtle */
  user-select: none;
}
.retry-toggle[aria-expanded="true"] {
  transform: rotate(90deg);
}
```

Sub-row visibility is toggled via `display: none` / `display: table-row` with no
height animation. Table row height animations are complex, fragile, and add no
meaningful UX value for a data table. Instant show/hide is the norm in data grids.

**State management**: Each grouped row stores its expanded state in a
`data-expanded="true|false"` attribute on the primary `<tr>`. The JS toggle handler
reads this attribute, flips it, and shows/hides the corresponding sub-rows (which
share a `data-parent-slug` attribute matching the primary row slug).

---

## Visual Hierarchy: Primary Row vs. Retry Sub-Rows

### Design principle: Sub-rows are subordinate context, not peers

The primary row (final outcome) must dominate. Sub-rows (prior failed attempts)
should be visually de-emphasized so users can scan the table without distraction
even when rows are expanded.

**Indentation**: Sub-row Item cell content is indented 24px from the left edge
(via padding-left: 36px, vs the normal 12px). This creates a clear parent-child
relationship.

**Background**: Sub-rows use a subtly tinted background:

```
.retry-sub-row > td {
  background: #f8fafc;     /* slate-50, very light gray */
  border-bottom: 1px solid #f1f5f9;  /* slate-100, lighter than normal rows */
}
```

**Text opacity**: Sub-row text is rendered at reduced opacity (0.7) to de-emphasize
without becoming unreadable:

```
.retry-sub-row > td {
  opacity: 0.7;
}
```

**Left accent border**: A 2px left border on the first cell of each sub-row,
colored to match the sub-row outcome badge, provides a subtle "thread" connecting
sub-rows to their parent:

```
.retry-sub-row > td:first-child {
  border-left: 2px solid #cbd5e1;  /* slate-300 */
  padding-left: 34px;              /* 36px indent minus 2px border */
}
```

**Hover behavior**: Sub-rows get a slightly different hover tint to maintain the
visual distinction from primary rows:

```
.retry-sub-row:hover > td {
  background: #f1f5f9;    /* slate-100, slightly darker than base */
  opacity: 0.85;           /* brighten slightly on hover */
}
```

**No disclosure triangle on sub-rows**: Sub-rows are leaf nodes. They show only
a dash or bullet prefix to indicate they are history entries:

```
Sub-row Item cell content: "  --- fix-auth-bug (attempt 1 of 3)"
```

The "attempt N of M" label in the sub-row Item cell tells the user the chronological
order of attempts, reading top-to-bottom as most-recent-first (matching the sort
order of the primary table).

**Hidden by default**: All sub-rows start with `display: none`. They become visible
only when the parent row is toggled open. The collapsed state is the default because
most dashboard scans are about current status, not history.

---

## Accessibility

### Keyboard Navigation

**Tab order**: The disclosure toggle in the Item cell receives focus via `tabindex="0"`
on the toggle span. When focused, pressing Enter or Space toggles expand/collapse.

**Focus indicator**: The toggle span gets a visible focus ring:

```
.retry-toggle:focus-visible {
  outline: 2px solid #3b82f6;  /* blue-500 */
  outline-offset: 2px;
  border-radius: 2px;
}
```

### ARIA Attributes

**On the toggle element**:
- `role="button"` -- communicates that this is an interactive control
- `aria-expanded="false"` -- toggled to "true" when sub-rows are visible
- `aria-label="Show retry history for {slug}"` -- descriptive label for screen readers

**On sub-rows**:
- `aria-hidden="true"` when collapsed (removed when expanded)
- Each sub-row `<tr>` is a standard table row, inheriting semantic `role="row"`

**Screen reader announcement flow**:
1. User tabs to the toggle: "Show retry history for fix-auth-bug, button, collapsed"
2. User presses Enter: sub-rows appear, announcement: "expanded"
3. User tabs through sub-rows as normal table rows
4. User returns to toggle and presses Enter: "collapsed"

### Color Contrast

All text colors meet WCAG 2.1 AA contrast requirements:
- Retry count badge: #475569 on #e2e8f0 = 4.8:1 ratio (passes AA)
- Sub-row text at 0.7 opacity: effective contrast remains above 4.5:1 against #f8fafc
- Disclosure triangle: #94a3b8 on white = 3.3:1 (decorative/large text exemption applies;
  the adjacent text label provides the accessible name)

---

## Cost and Duration Display Strategy

### Primary row: Aggregated cost, final-attempt duration

| Field | Primary Row Value | Rationale |
|---|---|---|
| Cost | Sum of all attempts | Users need the true total cost of getting an item to completion. Showing only the final attempt cost would hide the expense of retries. |
| Duration | Final attempt only | The duration of the successful run is what matters for performance assessment. Summing durations is misleading because retries may have failed fast. |
| Finished | Final attempt timestamp | When the item actually completed. |

This asymmetry (summed cost, final duration) matches user mental models:
- "How much did this cost me?" -> total across all attempts
- "How long does this take to run?" -> the attempt that actually succeeded

### Sub-row values: Per-attempt actuals

Each sub-row shows the individual attempt values:
- **Outcome**: The outcome of that specific attempt (warn, fail, etc.)
- **Cost**: The cost of that specific attempt
- **Duration**: The duration of that specific attempt
- **Finished**: The timestamp when that attempt finished

### Visual formatting

Sub-row cost and duration use the same `fmtCost()` and `fmtElapsed()` formatters
as the primary row. No special formatting is needed -- the visual hierarchy
(opacity, indentation, background) already communicates subordination.

The primary row cost column displays the aggregated cost with no special indicator.
The aggregation is implicit from the grouping. If the user wants the breakdown, they
expand the row.

---

## Template Structure

### Primary row (enhanced tpl-completion-row)

The existing template gains two conditional elements:

```html
<template id="tpl-completion-row">
  <tr data-expanded="false">
    <td class="completion-slug">
      <!-- If attempt_count > 1, prepend: -->
      <span class="retry-toggle" role="button" tabindex="0"
            aria-expanded="false" aria-label="Show retry history">&#x25B6;</span>
      <a href="/item/{slug}">{slug}</a>
    </td>
    <td class="completion-trace">
      <a class="trace-link" ...>Trace</a>
    </td>
    <td><span class="badge item-type-badge">{type}</span></td>
    <td>
      <span class="badge outcome-badge">{outcome}</span>
      <!-- If attempt_count > 1, append: -->
      <span class="badge retry-count-badge">x{attempt_count}</span>
    </td>
    <td class="completion-cost">{aggregated_cost}</td>
    <td class="completion-duration">{final_duration}</td>
    <td class="completion-finished">{final_finished}</td>
  </tr>
</template>
```

### New retry sub-row template

```html
<template id="tpl-retry-row">
  <tr class="retry-sub-row" data-parent-slug="{slug}" aria-hidden="true"
      style="display:none">
    <td class="completion-slug retry-sub-slug">
      --- {slug} (attempt {n} of {total})
    </td>
    <td class="completion-trace">
      <a class="trace-link" ...>Trace</a>
    </td>
    <td></td>  <!-- type badge omitted: same as parent -->
    <td><span class="badge outcome-badge">{attempt_outcome}</span></td>
    <td class="completion-cost">{attempt_cost}</td>
    <td class="completion-duration">{attempt_duration}</td>
    <td class="completion-finished">{attempt_finished}</td>
  </tr>
</template>
```

**Type badge omitted on sub-rows**: The item type is the same for all attempts (it is
a property of the item, not the execution). Repeating it adds noise. The empty cell
maintains column alignment.

---

## Interaction Flow Summary

1. **Default state**: Table shows one row per unique item slug. Items with retries
   show the final outcome badge plus a gray "x2" (or x3, etc.) count badge. A small
   disclosure triangle appears before the item name.

2. **User clicks/taps the Item cell or presses Enter on the toggle**: Sub-rows for
   prior attempts slide in below the primary row. The triangle rotates 90 degrees.
   The primary row remains visually dominant.

3. **Sub-rows visible**: User can scan each prior attempt: its outcome, individual
   cost, duration, and when it finished. Sub-rows are visually muted (lighter
   background, reduced opacity, indented).

4. **User clicks again or presses Enter**: Sub-rows collapse. Triangle rotates back.
   The table returns to the compact grouped view.

5. **Multiple expanded rows**: Each row operates independently. Users can expand
   several rows simultaneously to compare retry histories.

---

## Design -> AC Traceability

| AC | Addressed By | How |
|---|---|---|
| AC1 | Grouping by slug (D1/D2 data layer) + single primary row rendering | Retried items appear as one row |
| AC2 | Primary record is most-recent-per-slug | Grouped row shows the latest execution |
| AC3 | Sub-rows hidden by default, prior attempts only shown on expand | Prior attempts never clutter the main view |
| AC4 | Primary row outcome badge shows final status | Latest execution outcome is always the prominent badge |
| AC5 | Outcome badge + retry count badge visible without interaction | No click needed to see final status and that retries occurred |
| AC6 | Disclosure triangle + sub-rows with per-attempt outcomes | Toggle reveals full retry history with outcome per attempt |
| AC7 | Sub-rows start with display:none, aria-hidden:true | History hidden by default, requires explicit user action |
| AC8 | Sub-row template includes outcome, cost, duration, finished | Each prior attempt shows all key metrics |
