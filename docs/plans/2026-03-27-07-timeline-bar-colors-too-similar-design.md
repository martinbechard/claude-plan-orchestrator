# Design: Timeline Bar Colors Too Similar (Defect 07)

## Status: Review Required

The color palette fix was previously implemented. This plan validates the
existing implementation against the acceptance criteria and fixes any remaining
gaps.

## Architecture Overview

The timeline visualization is rendered in a single Jinja2 template:

- **langgraph_pipeline/web/templates/proxy_trace.html** -- contains:
  - bar_color(name) macro: maps run names to bar fill colors
  - text_color(name) macro: maps run names to text contrast colors
  - Legend section: hardcoded color swatches matching the macros
  - Grandchild bar and label rendering using the same macros

## Current State (Already Applied)

The bar_color macro already uses the target palette:
- Tool calls: #0891b2 (cyan/teal)
- LLM calls: #7c3aed (violet)
- Other: #f59e0b (amber)

The text_color macro uses appropriate contrast colors:
- Tool: #ecfeff (light cyan)
- LLM: #f5f3ff (light violet)
- Other: #1c1917 (dark, for amber background)

Legend fills match the bar_color values.

## Remaining Review Items

1. Verify no stale old colors (#16a34a green, #2563eb blue) remain in bar or
   legend rendering
2. Confirm the grandchild label text (#64748b slate) is intentional -- this is
   a label text color, not a bar category color, so it is acceptable
3. Visual spot-check that all bar types render with correct colors

## Key Files

- langgraph_pipeline/web/templates/proxy_trace.html (validate only)

## Design Decisions

- No code changes expected -- this is a validation-only pass
- If any stale colors are found, update them to match the palette above
