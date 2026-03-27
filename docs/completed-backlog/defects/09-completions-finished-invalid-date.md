# Recent Completions: Finished column shows "Invalid Date"

## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


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




## 5 Whys Analysis

Title: Inconsistent timestamp format serialization between DB proxy and in-memory implementations

Clarity: 4

5 Whys:

1. Why does the dashboard show "Invalid Date"?
   - Because fmtFinished() receives finished_at as an ISO 8601 string from the DB proxy, multiplies it by 1000 (yielding NaN), and new Date(NaN) renders as "Invalid Date".

2. Why does fmtFinished() attempt to multiply by 1000?
   - Because it was designed to handle finished_at as a Unix timestamp in seconds, requiring conversion to milliseconds for JavaScript's Date constructor.

3. Why does the DB proxy return ISO 8601 strings while the in-memory fallback returns Unix timestamps?
   - Because each implementation serializes timestamps using its native format: the DB proxy returns database-native timestamp strings, while the Python in-memory fallback stores Python's time.time() floats.

4. Why weren't these format differences caught during implementation or testing?
   - Because the in-memory path was tested and worked, but the DB proxy path was never validated against the same fmtFinished() function, creating a gap in test coverage.

5. Why do two implementations of the same data source have different serialization formats for the same field?
   - Because there's no shared contract or interface definition ensuring both backends serialize timestamps consistently before sending to the UI layer.

Root Need: Establish a canonical timestamp format contract at the backend-to-frontend boundary so all data sources return the same type, preventing UI code from needing to handle multiple formats.

Summary: The defect reveals a missing serialization contract between backend implementations that forces UI code to be polymorphic instead of having a single source of truth for timestamp format.
