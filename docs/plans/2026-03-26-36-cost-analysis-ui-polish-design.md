# Design: Cost Analysis UI Polish (Item 36)

## Overview

Two focused UI fixes to `langgraph_pipeline/web/templates/analysis.html` and
`langgraph_pipeline/web/static/style.css`:

1. Replace the two disclaimer lines at the top of the page with a collapsible
   info icon/button that reveals the text on click.
2. Fix the pagination styling: add left padding, increase page-count font size,
   and improve visual alignment with the table.

## Files to Modify

- `langgraph_pipeline/web/templates/analysis.html` — template changes
- `langgraph_pipeline/web/static/style.css` — CSS for info button and pagination fix

## Design Decisions

### Disclaimer collapse

Current state (lines 90-96 in analysis.html):

```html
<p style="font-size:13px;color:#666;margin-top:-0.5rem;">
  API-Equivalent Estimates — subscription charges may differ.
</p>
<div class="tool-call-note" role="note">
  Cost is recorded at the agent task level only. Tool calls carry no direct cost.
</div>
```

Replacement: a single inline info icon button (`ⓘ`) next to the `<h1>` that
toggles a hidden `<div>` containing both lines. No JavaScript framework needed —
plain inline `<script>` or a `<details>`/`<summary>` element.

Use `<details>`/`<summary>` for zero-JS toggle. The summary holds the icon; the
detail body holds both disclaimer lines. This is accessible, no-JS, and compact.

### Pagination fix

Current `style.css` `.pagination` rule has `padding: 0.75rem 0` (no left padding)
and `font-size: 13px`. The "Page N of M" span blends with surrounding text.

Fix:
- Add `padding-left: 0` at the table level is not appropriate; the pagination
  `<nav>` sits directly under `<div class="table-wrap">`, which has left margin
  from the section. The fix is to add explicit `padding-left` to `.pagination`
  matching the table cell left-padding, and to give the page counter span a
  slightly larger, higher-contrast style.
- `.pagination` gets `padding: 0.75rem 0 0.75rem 2px` (minimal, matching table
  cell padding-left of 8px in base styles).
- Add `.pagination-page-info` class with `font-size: 14px; font-weight: 500;
  color: #333;`.

## No New Files

All changes are inline edits to the two existing files.
