# Cost by Node Type Display Bugs — Design

## Problem

Two display bugs in the "Total Cost by Node Type" SVG chart and table:

1. **"E" label on top bar**: The SVG value label for the maximum-value bar is
   placed at `x = SVG_BAR_LABEL_PADDING + bar_area_width + SVG_TEXT_OFFSET_X`,
   which equals approximately `width - SVG_VALUE_LABEL_PADDING + SVG_TEXT_OFFSET_X`.
   With `SVG_VALUE_LABEL_PADDING = 10` and `SVG_TEXT_OFFSET_X = 5`, the text
   starts only 5px before the right SVG edge. The long float string
   `"55.605055300000004"` (~18 chars x 7px = ~126px) extends far beyond the
   viewport, leaving barely a sliver visible — which browser rendering may
   display as a partial glyph resembling "E".

2. **Full floating-point precision**: `svg_bar_chart` uses `{value:,}` (integer
   comma format) on float values, producing `55.605055300000004` instead of
   `$55.61`. The table in `analysis.html` uses `"%.4f"` for the node type rows.

## Root Cause

- `svg_bar_chart` in `cost_log_reader.py` has `values: list[int]` type and
  `{value:,}` display format — designed for integer counts, not USD floats.
- `SVG_VALUE_LABEL_PADDING = 10` is too small to reserve space for a formatted
  dollar amount label to the right of the max-width bar.
- `analysis.html` node type table uses `"%.4f"` instead of `"%.2f"`.

## Fix

### `langgraph_pipeline/web/cost_log_reader.py`

- Increase `SVG_VALUE_LABEL_PADDING` from `10` to `60` (enough for `$999.99`).
- Add optional `value_formatter` callable parameter to `svg_bar_chart`
  (default: `lambda v: f"${v:.2f}"`). Change `{value:,}` to
  `value_formatter(value)`.
- Update type annotation `values: list[int]` to `values: list[float]`.

### `langgraph_pipeline/web/templates/analysis.html`

- In the "Cost by node type" table, change `"%.4f"` to `"%.2f"` for
  `nc.total_cost_usd` and `nc.avg_cost_usd`.

### `tests/langgraph/web/test_cost_log_reader.py`

- Update any `svg_bar_chart` tests that check value label text to expect the
  `$X.XX` format and verify the label fits within the SVG width.

## Key Files

| File | Change |
|------|--------|
| `langgraph_pipeline/web/cost_log_reader.py` | `SVG_VALUE_LABEL_PADDING`, `svg_bar_chart` signature and value format |
| `langgraph_pipeline/web/templates/analysis.html` | Node type table precision |
| `tests/langgraph/web/test_cost_log_reader.py` | Update format assertions |

## Non-Goals

- Fixing the tilde prefix elsewhere on the page (separate item).
- The `value_formatter` default will also fix the daily cost chart float display
  as a side effect, which is acceptable.
