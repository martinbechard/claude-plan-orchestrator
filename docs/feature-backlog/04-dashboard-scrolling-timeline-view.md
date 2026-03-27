# Dashboard: scrolling timeline view for active workers

## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


## Status: Open

## RETURNED FROM COMPLETED — No Visible Implementation

This item was previously marked as completed but there is no evidence of the
implementation in the dashboard UI. No timeline toggle button exists, no
timeline view is rendered. Needs re-verification and completion.

## Priority: Medium

## Summary

Add an optional timeline view to the dashboard Active Workers section. Each
worker gets its own horizontal lane showing elapsed time as a growing bar,
updated live via the existing SSE feed. The view is toggled on/off so users
who prefer the compact table keep it.

## Expected Behavior

- A "Timeline" toggle button switches between the current table view and the
  new timeline view for active workers.
- The timeline is a live SVG (or CSS) chart with one row per active worker.
- Each row shows: worker slug label on the left, a bar growing rightward
  as elapsed time increases, and a live elapsed clock on the right.
- The time axis shows elapsed seconds/minutes from the earliest active
  worker's start. It scrolls or re-scales as workers run longer.
- Bar color indicates item type (defect / feature / analysis) — distinct
  palette, not the same colours as the trace Gantt.
- When a worker completes it briefly flashes its outcome colour
  (green/amber/red) then disappears from the timeline.
- The toggle preference is persisted in localStorage so it survives page
  refresh.

## Implementation Notes

- The SSE /api/state payload already delivers active_workers with
  elapsed_s per worker; no backend changes needed for the basic view.
- The timeline can be rendered as an HTML/CSS flexbox chart (div widths as
  percentages) rather than SVG to keep it simple and responsive.
- Re-scale the time axis on each SSE tick based on the longest elapsed_s
  among active workers.
- The toggle button should sit in the Active Workers section header, next
  to the section title.
