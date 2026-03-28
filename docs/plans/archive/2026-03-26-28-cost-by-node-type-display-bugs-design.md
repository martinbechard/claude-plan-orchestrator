# Cost by Node Type: Display Bugs Design

## Overview

Two bugs exist in `svg_bar_chart()` in `cost_log_reader.py` when rendering the
"Total Cost by Node Type" chart on the `/analysis` page:

1. The top bar's value label is clipped — the bar fills nearly all of the chart's
   drawable area, leaving fewer pixels than the value label requires.
2. Cost values display with full floating-point precision (e.g.
   `55.605055300000004`) because the function was written for integer values but is
   called with `float` costs and uses `{value:,}` without precision control.

## Root Cause

`svg_bar_chart` reserves `SVG_VALUE_LABEL_PADDING = 10` pixels to the right of
bars for value labels. A label like `$55.61` is ~35-40 pixels wide at 12px font,
so a bar that fills close to `bar_area_width` leaves the label clipped or pushed
outside the SVG viewport.

The function signature declares `values: list[int]` but the two callers in
`analysis.py` pass `list[float]`. Python's `{value:,}` on a float renders all
significant digits.

## Fix

### 1. Reserve enough space for value labels

Increase `SVG_VALUE_LABEL_PADDING` from `10` to `80`. This reserves 80 pixels to
the right of every bar for the formatted value label, preventing clipping even for
labels like `$55.61` at 12px font.

`bar_area_width` is calculated as `width - SVG_BAR_LABEL_PADDING - SVG_VALUE_LABEL_PADDING`,
so increasing the padding shrinks the bar area proportionally. The bars remain
proportional to each other; only the maximum bar width decreases slightly.

### 2. Format cost values to 2 decimal places with "$" prefix

Change `values: list[int]` to `values: list[float]` in `svg_bar_chart` and
update the value label rendering from `{value:,}` to `f"${value:.2f}"`.

Both existing callers (`_build_cost_over_time_svg` and `_build_node_cost_svg`)
pass USD float values, so the "$" prefix and 2-decimal formatting is correct for
both. This matches the project convention that cost values display as plain
`$0.0123` without tilde.

## Key Files

- `langgraph_pipeline/web/cost_log_reader.py` - `svg_bar_chart()` function and
  `SVG_VALUE_LABEL_PADDING` constant
- `tests/langgraph/web/test_cost_log_reader.py` - existing SVG bar chart tests
  need to be updated to pass float values and assert `$`-prefixed formatted labels

## Design Decisions

- No change to the callers in `analysis.py` — the fix belongs in the chart
  function, not the callers.
- `SVG_VALUE_LABEL_PADDING = 80` is sufficient for any realistic USD cost label
  up to 7 characters (`$999.99`) at 12px font (~7px/char = ~49px), with margin.
- Changing the type annotation from `list[int]` to `list[float]` corrects the
  existing mismatch; the chart works identically for integer values passed as
  floats.
