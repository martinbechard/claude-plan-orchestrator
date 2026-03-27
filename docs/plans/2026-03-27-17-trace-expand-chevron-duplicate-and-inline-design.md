# Design: Trace Detail — Fix Expand Chevron Duplicate and Inline Subrun Content (Review)

## Summary

This is a review pass for defect 17. A prior implementation addressed both issues:

1. **Duplicate chevron** — CSS rules in `style.css` (lines 192-197) now suppress the native
   disclosure widget on `.grandchild-toggle summary` and use only the `::before` pseudo-element.
2. **Inline subrun details** — `proxy_trace.html` (lines 319-360) renders grandchild name,
   duration, elapsed offset, error, and collapsible inputs/outputs JSON inline instead of
   a navigation link.

The work item status is "Review Required" — the implementation needs validation to confirm
the CSS chevron toggle works correctly (single chevron, no duplicate) and that inline details
render as expected across browsers.

## Architecture

### Key Files

| File | Current State |
|---|---|
| `langgraph_pipeline/web/static/style.css` | Lines 192-197: `.grandchild-toggle summary` has `list-style: none`, `::-webkit-details-marker { display: none }`, and `::before` chevron |
| `langgraph_pipeline/web/templates/proxy_trace.html` | Lines 319-360: Grandchild inline panel with name, duration, elapsed, error, inputs/outputs JSON blocks |

### Potential Issue: Open-State Chevron

The closed-state chevron is set by `.grandchild-toggle summary::before { content: "▶ "; }` (specificity 0,1,1).
The open-state relies on the generic rule `details[open] > summary::before { content: "▼"; }` (specificity 0,1,2).
The generic rule has higher specificity, so the chevron should toggle correctly.

However, the closed state uses "▶ " (with trailing space) while the open state uses "▼" (no trailing space).
This inconsistency may cause a minor layout shift. The fix task should verify and normalize this.

## Design Decisions

- Reuse the existing implementation; do not rewrite from scratch.
- Validate both the CSS chevron behavior and the inline content rendering.
- Fix any remaining inconsistencies found during review.
