# Design: Timeline Bar Colors Too Similar

## Context

The timeline Gantt chart in proxy_trace.html used green/blue/grey bar colors that
were hard to distinguish, especially for users with color vision differences.

## Current State

A prior implementation already updated the color palette:
- LLM calls: #7c3aed (violet)
- Tool calls: #0891b2 (cyan/teal)
- Other/chain: #f59e0b (amber)

The bar_color() macro, text_color() macro, and legend fills all reference
the new palette. One remaining #64748b is used for grandchild label text (neutral
UI text, not a category color).

## Key File

- langgraph_pipeline/web/templates/proxy_trace.html (lines 151-180 for macros,
  lines 331-335 for legend)

## Design Decision

This is a validation-only task. The fix was previously applied. The plan validates
that all acceptance criteria hold and fixes any remaining issues if found.
