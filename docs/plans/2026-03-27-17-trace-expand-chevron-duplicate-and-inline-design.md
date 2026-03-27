# Design: Trace Detail — Fix Expand Chevron Duplicate and Inline Subrun Content

## Summary

Defect 17 reports two problems on the trace detail page:
1. Clicking the expand chevron on a run row shows duplicate chevrons
2. Expanded content only shows a navigation link instead of inline subrun details

A prior implementation exists and addresses both issues. The item is marked "Review Required"
so validation is needed to confirm correctness.

## Current State

### CSS Fix (style.css lines 192-199)
- `.grandchild-toggle summary` suppresses native markers via `list-style: none`,
  `::-webkit-details-marker { display: none }`, and `::marker { display: none }`
- Custom `::before` pseudo-element renders chevron: "▶" closed, "▼" open

### Inline Panel (proxy_trace.html lines 319-360)
- Iterates `grandchildren_by_parent.get(child.run_id, [])` for each child run
- Renders name, duration, elapsed offset per grandchild
- Shows error message if present
- Collapsible inputs/outputs JSON blocks via nested `<details class="json-block">`

### Data Pipeline (routes/proxy.py)
- `get_children_batch()` fetches grandchildren in a single batch query
- Grandchildren enriched via `_enrich_run` and `_compute_elapsed`
- `grandchildren_by_parent` dict passed to template

## Key Files

| File | Role |
|---|---|
| `langgraph_pipeline/web/static/style.css` | Chevron CSS rules (lines 192-199) |
| `langgraph_pipeline/web/templates/proxy_trace.html` | Inline grandchild panels (lines 319-360) |
| `langgraph_pipeline/web/routes/proxy.py` | Grandchildren fetching and enrichment |
| `langgraph_pipeline/web/proxy.py` | `get_children_batch()` batch query |

## Potential Issue

The closed-state chevron uses "▶ " (trailing space) while the scoped open-state `.grandchild-toggle[open]`
uses "▼ " (also trailing space). The generic open rule `details[open] > summary::before` uses "▼" (no space).
The scoped rule has equal or higher specificity, so it should win. Validator should confirm.

## Design Decisions

- Reuse existing implementation; validate rather than rewrite
- CSS scoped to `.grandchild-toggle` to avoid breaking other `<details>` elements
- Single batch query for grandchildren (no N+1)
- Nested expand (great-grandchildren) out of scope
