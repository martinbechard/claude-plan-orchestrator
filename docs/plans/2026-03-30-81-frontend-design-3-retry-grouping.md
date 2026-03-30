# Frontend Implementation Design: Retry Grouping UI (Design 3)

Source item: tmp/plans/.claimed/81-dashboard-group-retries-per-item.md
Design overview: docs/plans/2026-03-30-81-dashboard-group-retries-per-item-design.md
Requirements: docs/plans/2026-03-30-81-dashboard-group-retries-per-item-requirements.md

## Overview

This document specifies the concrete frontend changes to dashboard.js,
dashboard.html, and style.css that implement the grouped retry UI for the
dashboard completions table. The backend (D1, D2) provides grouped completions
where each entry has an `attempt_count` integer and a `retries` array of
prior-attempt objects. This design covers how the frontend renders that data
with a retry count badge, disclosure toggle, and expandable sub-rows.

### Data contract (input from backend)

Each entry in the `recent_completions` SSE array gains two fields:

```
{
  slug: "78-item-archived-as-success",
  item_type: "defect",
  outcome: "success",          // final outcome (most recent attempt)
  cost_usd: 0.42,             // cost of the final attempt
  duration_s: 127,            // duration of the final attempt
  finished_at: "2026-03-30T14:22:00Z",
  run_id: "abc-123",
  attempt_count: 3,           // total attempts including final
  retries: [                  // prior attempts, newest-first
    {
      outcome: "warn",
      cost_usd: 0.38,
      duration_s: 95,
      finished_at: "2026-03-30T13:50:00Z",
      run_id: "abc-122"
    },
    {
      outcome: "fail",
      cost_usd: 0.12,
      duration_s: 42,
      finished_at: "2026-03-30T13:00:00Z",
      run_id: "abc-121"
    }
  ]
}
```

When `attempt_count` is 1, `retries` is an empty array. The primary row always
represents the most recent (final) attempt.

---

## 1. Retry Count Badge (D3 -- AC4, AC5)

### Goal

Show a small badge next to the outcome badge that communicates at-a-glance how
many attempts occurred, without requiring any interaction.

### Template change (dashboard.html)

Add a `<span class="retry-count-badge">` immediately after the outcome badge
inside the `tpl-completion-row` template. It is hidden by default and only
populated by JS when `attempt_count > 1`.

```html
<template id="tpl-completion-row">
  <tr>
    <td class="completion-slug"></td>
    <td class="completion-trace">
      <a class="trace-link" href="#" target="_blank" rel="noopener"
         style="display:none" aria-label="View trace">Trace</a>
    </td>
    <td><span class="badge item-type-badge"></span></td>
    <td class="completion-outcome-cell">
      <span class="badge outcome-badge"></span>
      <span class="retry-count-badge" style="display:none"
            aria-label="Retry count"></span>
    </td>
    <td class="completion-cost" style="text-align:right"></td>
    <td class="completion-duration" style="text-align:right"></td>
    <td class="completion-finished"></td>
  </tr>
</template>
```

Key points:
- The outcome `<td>` gets a class `completion-outcome-cell` so both badges
  can sit side by side with controlled spacing.
- The retry badge uses `style="display:none"` by default; JS shows it only
  when `attempt_count > 1`.
- The badge text format is the multiplication sign followed by the count,
  e.g. "x3" for three total attempts.

### CSS (style.css)

```css
/* Retry count badge next to outcome */
.completion-outcome-cell {
    white-space: nowrap;
}

.retry-count-badge {
    display: inline-block;
    margin-left: 6px;
    padding: 1px 6px;
    border-radius: 10px;
    font-size: 10px;
    font-weight: 700;
    background: #e2e8f0;
    color: #475569;
    vertical-align: middle;
    letter-spacing: 0.02em;
}
```

### JS logic (dashboard.js)

Inside `renderCompletions()`, after populating the outcome badge:

```javascript
var retryBadge = clone.querySelector(".retry-count-badge");
if (c.attempt_count > 1) {
    retryBadge.textContent = "x" + c.attempt_count;
    retryBadge.setAttribute("aria-label", c.attempt_count + " attempts");
    retryBadge.style.display = "";
}
```

---

## 2. Disclosure Toggle on Primary Row (D4 -- AC6, AC7)

### Goal

Rows with retries get a clickable disclosure triangle in the slug cell. Clicking
it expands or collapses sub-rows showing prior attempts.

### Template change (dashboard.html)

The slug cell in `tpl-completion-row` gains a toggle button that is hidden by
default. The toggle is a `<button>` with a disclosure triangle character, placed
before the slug link. Using a `<button>` ensures keyboard accessibility
(focusable, activatable with Enter/Space).

```html
<td class="completion-slug">
    <button class="retry-toggle" type="button"
            aria-expanded="false" aria-label="Show retry history"
            style="display:none">&#9654;</button>
    <!-- slug link appended by JS -->
</td>
```

### CSS (style.css)

```css
/* Disclosure toggle for retry rows */
.retry-toggle {
    background: none;
    border: none;
    cursor: pointer;
    font-size: 9px;
    color: #9090b0;
    padding: 2px 4px;
    margin-right: 4px;
    transition: transform 0.15s ease;
    vertical-align: middle;
    line-height: 1;
}

.retry-toggle:hover {
    color: #3b6fcf;
}

.retry-toggle:focus-visible {
    outline: 2px solid #3b6fcf;
    outline-offset: 1px;
    border-radius: 2px;
}

.retry-toggle[aria-expanded="true"] {
    transform: rotate(90deg);
}
```

The rotation from right-pointing triangle (&#9654;) by 90 degrees creates the
"open" state pointing down, which is a standard disclosure pattern.

### JS logic (dashboard.js)

Inside `renderCompletions()`, when `attempt_count > 1`:

```javascript
if (c.attempt_count > 1 && c.retries && c.retries.length > 0) {
    var toggle = clone.querySelector(".retry-toggle");
    toggle.style.display = "";
    var primaryRow = clone.querySelector("tr");
    primaryRow.setAttribute("data-slug", c.slug);
    primaryRow.setAttribute("data-has-retries", "true");

    toggle.addEventListener("click", function(evt) {
        evt.stopPropagation();
        var row = evt.target.closest("tr");
        var expanded = row.getAttribute("data-expanded") === "true";
        toggleRetryRows(row, c.retries, !expanded);
    });
}
```

---

## 3. Retry Sub-Row Template and DOM Insertion (D4 -- AC6, AC7, AC8)

### Goal

When the toggle is clicked, insert sub-rows immediately after the primary row in
the `<tbody>`. Each sub-row shows one prior attempt with outcome, cost, duration,
and finished time. Clicking again removes the sub-rows.

### New template (dashboard.html)

```html
<template id="tpl-retry-row">
  <tr class="retry-sub-row">
    <td class="retry-sub-slug">
      <span class="retry-attempt-label"></span>
    </td>
    <td class="retry-sub-trace">
      <a class="trace-link" href="#" target="_blank" rel="noopener"
         style="display:none" aria-label="View trace">Trace</a>
    </td>
    <td></td>
    <td><span class="badge outcome-badge"></span></td>
    <td class="retry-sub-cost" style="text-align:right"></td>
    <td class="retry-sub-duration" style="text-align:right"></td>
    <td class="retry-sub-finished"></td>
  </tr>
</template>
```

Key points:
- The slug cell shows an attempt label like "Attempt 2" or "Attempt 1" instead
  of the slug (which is already visible on the parent row).
- The type cell is empty (same type as parent).
- The trace cell has its own trace link for the specific run_id.
- The class `retry-sub-row` enables distinct styling.

### CSS (style.css)

```css
/* Retry sub-rows */
.retry-sub-row {
    background: #f8fafc;
}

.retry-sub-row > td {
    padding: 5px 12px;
    font-size: 12px;
    color: #6b7280;
    border-bottom: 1px solid #f0f0f5;
}

.retry-sub-row:hover > td {
    background: #f1f5f9;
}

.retry-sub-slug {
    padding-left: 36px !important;
}

.retry-attempt-label {
    font-size: 11px;
    font-style: italic;
    color: #9090b0;
}

/* Muted outcome badges on sub-rows */
.retry-sub-row .outcome-badge {
    opacity: 0.75;
    font-size: 10px;
}
```

The `padding-left: 36px` indentation visually nests sub-rows under the parent.
The muted background (#f8fafc) and reduced font size distinguish sub-rows from
primary rows. The `!important` on the padding override is acceptable here because
table cell padding specificity makes normal overrides verbose.

### JS: toggleRetryRows function (dashboard.js)

New function added to the Render helpers section:

```javascript
/**
 * Inserts or removes retry sub-rows after the given primary row.
 * @param {HTMLTableRowElement} primaryRow - The <tr> for the grouped entry.
 * @param {Array} retries - Array of prior-attempt objects (newest-first).
 * @param {boolean} expand - true to insert sub-rows, false to remove.
 */
function toggleRetryRows(primaryRow, retries, expand) {
    var toggle = primaryRow.querySelector(".retry-toggle");
    var slug = primaryRow.getAttribute("data-slug");

    // Remove existing sub-rows for this slug
    var existing = primaryRow.parentNode.querySelectorAll(
        'tr.retry-sub-row[data-parent-slug="' + slug + '"]'
    );
    existing.forEach(function(el) { el.remove(); });

    if (expand) {
        toggle.setAttribute("aria-expanded", "true");
        primaryRow.setAttribute("data-expanded", "true");
        toggle.setAttribute("aria-label", "Hide retry history");

        var totalAttempts = retries.length + 1;
        var fragment = document.createDocumentFragment();

        retries.forEach(function(r, idx) {
            var clone = stampTemplate("tpl-retry-row");
            var subRow = clone.querySelector("tr");
            subRow.setAttribute("data-parent-slug", slug);

            // Attempt number: retries are newest-first, so first retry
            // is attempt (totalAttempts - 1), etc.
            var attemptNum = totalAttempts - 1 - idx;
            clone.querySelector(".retry-attempt-label").textContent =
                "Attempt " + attemptNum;

            var outcomeEl = clone.querySelector(".outcome-badge");
            outcomeEl.textContent = r.outcome;
            outcomeEl.classList.add(outcomeBadgeClass(r.outcome));

            clone.querySelector(".retry-sub-cost").textContent =
                fmtCost(r.cost_usd);
            clone.querySelector(".retry-sub-duration").textContent =
                fmtElapsed(r.duration_s || 0);
            clone.querySelector(".retry-sub-finished").textContent =
                fmtFinished(r.finished_at);

            var traceLink = clone.querySelector(".trace-link");
            if (r.run_id) {
                traceLink.href = "/proxy?trace_id=" +
                    encodeURIComponent(r.run_id);
                traceLink.style.display = "";
            }

            fragment.appendChild(clone);
        });

        // Insert sub-rows immediately after the primary row
        primaryRow.after(fragment);
    } else {
        toggle.setAttribute("aria-expanded", "false");
        primaryRow.setAttribute("data-expanded", "false");
        toggle.setAttribute("aria-label", "Show retry history");
    }
}
```

Key design choices:
- **Idempotent removal first**: Always remove existing sub-rows before inserting
  to prevent duplicates if the function is called during a re-render.
- **data-parent-slug attribute**: Links sub-rows to their parent for reliable
  cleanup, even when the table is re-rendered by SSE updates.
- **DocumentFragment**: Batches DOM insertions for performance.
- **after() method**: Inserts the fragment as siblings immediately following the
  primary row, maintaining table row order.

---

## 4. Re-render Preservation (SSE update handling)

### Problem

`renderCompletions()` currently wipes and rebuilds all rows on every SSE event.
This destroys expanded sub-rows. The design must handle this gracefully.

### Approach: Preserve expanded state in a module-level Set

Add a module-level variable to track which slugs are currently expanded:

```javascript
var expandedRetrySlugs = new Set();
```

In `toggleRetryRows`, update this set:

```javascript
if (expand) {
    expandedRetrySlugs.add(slug);
    // ... insert sub-rows ...
} else {
    expandedRetrySlugs.delete(slug);
    // ... remove sub-rows ...
}
```

At the end of `renderCompletions()`, after appending all primary rows, restore
expanded state for any slugs that were previously expanded:

```javascript
// Restore expanded retry sub-rows after re-render
expandedRetrySlugs.forEach(function(slug) {
    var match = completions.find(function(c) { return c.slug === slug; });
    if (match && match.retries && match.retries.length > 0) {
        var row = tbody.querySelector('tr[data-slug="' + slug + '"]');
        if (row) {
            toggleRetryRows(row, match.retries, true);
        }
    } else {
        // Slug no longer in completions or no longer has retries
        expandedRetrySlugs.delete(slug);
    }
});
```

This ensures that:
1. Expanded rows survive SSE re-renders.
2. Stale expanded slugs (items that left the recent completions window) are
   automatically cleaned up.
3. No flickering -- the primary row and sub-rows are inserted in the same
   paint cycle via fragment appending.

---

## 5. Updated renderCompletions() (full function)

For clarity, here is the complete updated function with all changes integrated:

```javascript
function renderCompletions(completions) {
    var tbody = document.getElementById("completions-container");
    var emptyRow = document.getElementById("completions-empty");

    if (!completions || completions.length === 0) {
        emptyRow.style.display = "";
        Array.from(tbody.querySelectorAll("tr:not(#completions-empty)"))
            .forEach(function(el) { el.remove(); });
        expandedRetrySlugs.clear();
        return;
    }

    emptyRow.style.display = "none";

    var fragment = document.createDocumentFragment();
    completions.forEach(function(c) {
        var clone = stampTemplate("tpl-completion-row");

        var completionSlugEl = clone.querySelector(".completion-slug");

        // Add toggle button for items with retries
        var hasRetries = c.attempt_count > 1 && c.retries &&
            c.retries.length > 0;

        var toggle = clone.querySelector(".retry-toggle");
        if (hasRetries) {
            toggle.style.display = "";
        }

        var completionSlugLink = document.createElement("a");
        completionSlugLink.href = "/item/" + encodeURIComponent(c.slug);
        completionSlugLink.textContent = c.slug;
        completionSlugEl.appendChild(completionSlugLink);

        var typeEl = clone.querySelector(".item-type-badge");
        typeEl.textContent = c.item_type;
        typeEl.classList.add(itemTypeBadgeClass(c.item_type));

        var outcomeEl = clone.querySelector(".outcome-badge");
        outcomeEl.textContent = c.outcome;
        outcomeEl.classList.add(outcomeBadgeClass(c.outcome));

        // Show retry count badge
        var retryBadge = clone.querySelector(".retry-count-badge");
        if (c.attempt_count > 1) {
            retryBadge.textContent = "x" + c.attempt_count;
            retryBadge.setAttribute("aria-label",
                c.attempt_count + " attempts");
            retryBadge.style.display = "";
        }

        clone.querySelector(".completion-cost").textContent =
            fmtCost(c.cost_usd);
        clone.querySelector(".completion-duration").textContent =
            fmtElapsed(c.duration_s || 0);
        clone.querySelector(".completion-finished").textContent =
            fmtFinished(c.finished_at);

        var traceLink = clone.querySelector(".trace-link");
        if (c.run_id) {
            traceLink.href = "/proxy?trace_id=" +
                encodeURIComponent(c.run_id);
            traceLink.style.display = "";
        } else {
            traceLink.style.display = "none";
        }

        // Wire toggle click handler
        var primaryRow = clone.querySelector("tr");
        primaryRow.setAttribute("data-slug", c.slug);
        if (hasRetries) {
            primaryRow.setAttribute("data-has-retries", "true");
            (function(row, retries) {
                toggle.addEventListener("click", function(evt) {
                    evt.stopPropagation();
                    var expanded =
                        row.getAttribute("data-expanded") === "true";
                    toggleRetryRows(row, retries, !expanded);
                });
            })(primaryRow, c.retries);
        }

        fragment.appendChild(clone);
    });

    Array.from(tbody.querySelectorAll("tr:not(#completions-empty)"))
        .forEach(function(el) { el.remove(); });
    tbody.appendChild(fragment);

    // Restore expanded state after re-render
    expandedRetrySlugs.forEach(function(slug) {
        var match = completions.find(function(c) {
            return c.slug === slug;
        });
        if (match && match.retries && match.retries.length > 0) {
            var row = tbody.querySelector(
                'tr[data-slug="' + slug + '"]');
            if (row) {
                toggleRetryRows(row, match.retries, true);
            }
        } else {
            expandedRetrySlugs.delete(slug);
        }
    });
}
```

The IIFE closure `(function(row, retries) { ... })(primaryRow, c.retries)`
captures the correct `row` and `retries` references for each iteration,
avoiding the classic closure-in-a-loop bug with `var`.

---

## 6. Accessibility

| Concern | Solution |
|---|---|
| Toggle keyboard access | `<button>` element is natively focusable and activatable with Enter/Space |
| Expanded state | `aria-expanded="true/false"` on the toggle button |
| Toggle purpose | `aria-label="Show retry history"` / `"Hide retry history"` changes on toggle |
| Retry count | `aria-label="3 attempts"` on the badge for screen readers |
| Sub-row association | `data-parent-slug` links sub-rows to parent; screen readers read them as consecutive table rows under the same slug context |

---

## 7. Complete CSS additions

All CSS additions are listed here for reference. They follow the existing
style.css patterns (consistent spacing, color palette, transition timing).

```css
/* ── Dashboard -- Retry grouping ──────────────────────────────────────────── */

/* Outcome cell layout for badge + retry count */
.completion-outcome-cell {
    white-space: nowrap;
}

/* Retry count badge */
.retry-count-badge {
    display: inline-block;
    margin-left: 6px;
    padding: 1px 6px;
    border-radius: 10px;
    font-size: 10px;
    font-weight: 700;
    background: #e2e8f0;
    color: #475569;
    vertical-align: middle;
    letter-spacing: 0.02em;
}

/* Disclosure toggle */
.retry-toggle {
    background: none;
    border: none;
    cursor: pointer;
    font-size: 9px;
    color: #9090b0;
    padding: 2px 4px;
    margin-right: 4px;
    transition: transform 0.15s ease;
    vertical-align: middle;
    line-height: 1;
}

.retry-toggle:hover {
    color: #3b6fcf;
}

.retry-toggle:focus-visible {
    outline: 2px solid #3b6fcf;
    outline-offset: 1px;
    border-radius: 2px;
}

.retry-toggle[aria-expanded="true"] {
    transform: rotate(90deg);
}

/* Retry sub-rows */
.retry-sub-row {
    background: #f8fafc;
}

.retry-sub-row > td {
    padding: 5px 12px;
    font-size: 12px;
    color: #6b7280;
    border-bottom: 1px solid #f0f0f5;
}

.retry-sub-row:hover > td {
    background: #f1f5f9;
}

.retry-sub-slug {
    padding-left: 36px !important;
}

.retry-attempt-label {
    font-size: 11px;
    font-style: italic;
    color: #9090b0;
}

.retry-sub-row .outcome-badge {
    opacity: 0.75;
    font-size: 10px;
}
```

---

## 8. Files changed summary

| File | Change |
|---|---|
| `langgraph_pipeline/web/static/dashboard.js` | Add `expandedRetrySlugs` Set, `toggleRetryRows()` function, update `renderCompletions()` |
| `langgraph_pipeline/web/templates/dashboard.html` | Modify `tpl-completion-row` (add toggle button, retry badge, outcome cell class), add `tpl-retry-row` template |
| `langgraph_pipeline/web/static/style.css` | Add retry grouping CSS block (~50 lines) |

No new files are created. All changes are additive modifications to three
existing files.

---

## 9. Backward compatibility

The design is fully backward-compatible with non-grouped data:
- If `attempt_count` is undefined or 1, the retry badge stays hidden and no
  toggle is rendered. The row looks identical to the current design.
- If `retries` is undefined or empty, the toggle logic is never wired.
- The `expandedRetrySlugs` set handles missing slugs gracefully by deleting
  stale entries.

---

## Design -> AC Traceability

| AC | How addressed |
|---|---|
| AC1 | Backend groups by slug; frontend renders one primary row per group (Section 5) |
| AC2 | Primary row shows the final (most recent) attempt's data (inherits from existing renderCompletions logic + backend D1/D2) |
| AC3 | Prior attempts are only visible as sub-rows inside the toggle; never shown as top-level rows (Section 3) |
| AC4 | Final outcome badge is prominent on the primary row, unchanged from current design (Section 1) |
| AC5 | Retry count badge ("x3") visible without interaction; outcome visible without interaction (Section 1) |
| AC6 | Toggle control reveals sub-rows with per-attempt outcome, cost, duration, finished time (Sections 2, 3) |
| AC7 | Sub-rows hidden by default; only visible after explicit toggle click (Section 2, CSS default display:none) |
| AC8 | Each sub-row shows attempt outcome badge, cost, duration, and timestamp (Section 3 template) |
