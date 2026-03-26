# Cost by node type: bar labels clipped and numbers have unlimited precision

## Status: Open

## Priority: Medium

## Summary

Two display bugs in the "Total Cost by Node Type" section on the cost
analysis page:

1. The top bar value label is clipped — "$55.60" renders as just "5" or
   partial text because the SVG bar chart does not allocate enough space
   for the value label to the right of the bar. The bar fills most of the
   chart width leaving no room for the number.

2. Cost values display with full floating point precision (e.g.
   "55.605055300000004") instead of "$55.61".

## Fix

1. In svg_bar_chart() (cost_log_reader.py), ensure the value label has
   enough space: either cap the bar width to leave room for the label,
   or position the label inside the bar when the bar is wide.
2. Format all cost values to 2 decimal places with a "$" prefix before
   passing them to the chart (e.g. "$55.61" not "55.605055300000004").
3. Increase SVG_VALUE_LABEL_PADDING or adjust the bar_area_width
   calculation to reserve more space for labels.

## LangSmith Trace: ebd7169b-1c66-41cb-afc0-b625d3895aa1
