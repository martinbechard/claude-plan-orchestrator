# Cost by node type: bar labels clipped and numbers have unlimited precision

## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


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




## 5 Whys Analysis

Title: Bar labels clipped and cost values unformatted in cost analysis visualization

Clarity: 3/5

The defect clearly describes the symptoms and specific code areas, but doesn't expose the design decisions that led to these problems.

5 Whys:

1. **Why are the bar labels clipped?**
   → The SVG bar width fills most of the chart area without reserving space for the label that appears beside it.

2. **Why doesn't the bar width calculation reserve space for the label?**
   → The bar-drawing logic treats the bar as the primary element and doesn't account for the label's spatial requirements as part of the overall layout.

3. **Why isn't label space considered when designing the bar layout?**
   → The `svg_bar_chart()` function was built to render bars without an explicit specification defining how space should be allocated between data visualization and supplementary elements like labels.

4. **Why does this specification gap exist?**
   → Cost visualization components were developed incrementally to solve immediate display problems without establishing a reusable design pattern for composite visualizations.

5. **Why wasn't a design pattern established upfront?**
   → There's no enforced standard for how visualization components should handle layout composition, value formatting, and element spacing — these decisions are made ad-hoc per component.

Root Need: Establish a visualization component design standard that requires space allocation be defined for all elements (bars, labels, padding) before implementation, and enforce consistent value formatting at the data-to-display layer.

Summary: The defect reveals missing design discipline in visualization components — layout and formatting decisions were made independently rather than as part of a composed whole.
