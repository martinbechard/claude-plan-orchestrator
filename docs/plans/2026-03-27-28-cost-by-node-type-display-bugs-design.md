# Cost by Node Type: Display Bugs Design

## Overview

Defect 28 reported two display bugs in the "Total Cost by Node Type" SVG bar chart
on the /analysis page:

1. Top bar value label clipped (bar fills chart width, no room for label text)
2. Cost values shown with full float precision instead of formatted "$X.XX"

## Current State

A prior implementation pass applied fixes in cost_log_reader.py:

- SVG_VALUE_LABEL_PADDING set to 80 pixels (reserves space for value labels)
- svg_bar_chart() accepts values as list[float]
- value_formatter parameter defaults to lambda v: f"${v:.2f}"
- Value labels render via value_formatter(value) instead of raw floats
- bar_area_width = width - SVG_BAR_LABEL_PADDING - SVG_VALUE_LABEL_PADDING ensures
  bars never overflow into the label area

## Task

This is a "Review Required" item. The task is to verify the existing fix is correct
and complete:

1. Confirm svg_bar_chart() renders labels within the SVG viewport for realistic
   cost values (e.g. $55.61, $999.99)
2. Confirm both callers in analysis.py benefit from the default formatter
3. Ensure tests cover the clipping edge case (max-value bar with long label)
4. Fix any gaps found during validation

## Key Files

- langgraph_pipeline/web/cost_log_reader.py -- svg_bar_chart and constants
- langgraph_pipeline/web/routes/analysis.py -- callers of svg_bar_chart
- tests/langgraph/web/test_cost_log_reader.py -- SVG chart tests

## Design Decisions

- Keep the fix in svg_bar_chart() (not callers) -- formatting belongs in the
  chart rendering layer
- 80px value label padding is sufficient for labels up to ~11 chars at 12px font
- value_formatter callable allows callers to override if needed (e.g. for
  non-dollar values like token counts)
