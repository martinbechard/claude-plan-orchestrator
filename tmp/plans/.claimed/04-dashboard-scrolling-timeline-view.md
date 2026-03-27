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

## LangSmith Trace: 258e8fb3-50fa-403f-ae90-6c8b5c1d4153


## 5 Whys Analysis

# 5 Whys Analysis: Dashboard Timeline View

**Title:** Operators need real-time visibility into worker runtime to spot and intervene on slow/hung workers

**Clarity:** 4/5  
(Well-specified UI behavior and technical details; slight ambiguity on "scrolls or re-scales" timing)

**5 Whys:**

1. **Why does the dashboard need a timeline view for active workers?**
   - The current table view shows workers as a static list without temporal context—operators can't quickly see which workers have been running longest or visualize runtime progression, making slow/stuck workers invisible until they fail.

2. **Why is visualizing execution timeline important?**
   - Operators need to identify workers that are taking unexpectedly long while they're still running so they can manually terminate them and prevent cascading resource waste, rather than waiting passively for timeouts.

3. **Why can't operators use external monitoring (logs, metrics dashboards) instead?**
   - Real-time awareness must be in the active dashboard UI where operators are already focused; context-switching to external tools defeats the purpose of immediate observability during live pipeline execution.

4. **Why does manual intervention matter if timeouts exist?**
   - Timeout settings may be high (minutes/hours), missing, or unknown; early manual termination saves significant time and cost by stopping stuck workers much faster than waiting for timeout signals.

5. **Why is rapid failure recovery critical for this orchestration system?**
   - Workers hang due to external service failures, infinite loops, resource exhaustion, or deadlocks; without immediate human visibility and control, each hung worker wastes compute time and delays subsequent pipeline stages.

**Root Need:** Operators need real-time visual feedback on worker execution duration to identify and manually terminate slow/stuck workers during active pipeline runs, minimizing resource waste and accelerating recovery.

**Summary:** The feature closes an observability gap—making worker runtime duration immediately visible in the active workspace so operators can intervene on slow/hung workers before they consume significant resources.
