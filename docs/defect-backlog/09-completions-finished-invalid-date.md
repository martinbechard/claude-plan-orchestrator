# Recent Completions: Finished column shows "Invalid Date"

## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


## Status: Open

## Priority: High

## Summary

Every row in the Recent Completions table shows "Invalid Date" in the Finished
column.

## Root Cause

fmtFinished() in dashboard.js treats finished_at as a Unix timestamp number
and does `new Date(value * 1000)`. However when the DB proxy is enabled,
proxy.list_completions() returns finished_at as an ISO 8601 string (e.g.
"2026-03-26T05:11:53+00:00"). Multiplying a string by 1000 yields NaN, which
produces "Invalid Date".

The in-memory fallback path (DashboardState.recent_completions) stores
finished_at as time.time() (a float), so the function works there but breaks
with the DB path.

## Fix

In dashboard.js, update fmtFinished to handle both types:

    function fmtFinished(finishedAt) {
      const d = typeof finishedAt === "number"
        ? new Date(finishedAt * 1000)
        : new Date(finishedAt);
      return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    }
