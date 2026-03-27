# Design: Recent Completions "Invalid Date" Fix

## Problem

The Recent Completions table shows "Invalid Date" in the Finished column when
data comes from the DB proxy. The DB proxy returns finished_at as ISO 8601
strings, but fmtFinished() assumes Unix timestamp numbers and multiplies by
1000, producing NaN.

## Architecture

The dashboard UI (dashboard.js) receives completion data from two backends:

1. **In-memory fallback** (DashboardState) - returns finished_at as a float
   (Python time.time())
2. **DB proxy** (proxy.list_completions) - returns finished_at as an ISO 8601
   string (e.g. "2026-03-26T05:11:53+00:00")

The fmtFinished() function must handle both formats.

## Key Files to Modify

- **dashboard.js** (or equivalent) - Update fmtFinished() to detect the type
  of finishedAt and construct the Date object accordingly

## Design Decision

Handle both types at the UI boundary rather than normalizing at the backend.
This is the simplest fix: a typeof check in fmtFinished() to branch between
numeric (Unix timestamp * 1000) and string (direct ISO 8601 parse) paths.

This aligns with the backlog item's prescribed fix and avoids changing
serialization in either backend.
