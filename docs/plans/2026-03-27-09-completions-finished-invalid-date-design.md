# Design: Recent Completions "Invalid Date" Fix

## Problem

The Recent Completions table shows "Invalid Date" in the Finished column when
data comes from the DB proxy. The DB proxy returns finished_at as ISO 8601
strings, but the original fmtFinished() assumed Unix timestamp numbers and
multiplied by 1000, producing NaN.

## Architecture

The dashboard UI (dashboard.js) receives completion data from two backends:

1. **In-memory fallback** (DashboardState) - returns finished_at as a float
   (Python time.time())
2. **DB proxy** (proxy.list_completions) - returns finished_at as an ISO 8601
   string (e.g. "2026-03-26T05:11:53+00:00")

The fmtFinished() function must handle both formats.

## Current State

A prior fix added the finishedAtToMs() helper in dashboard.js that uses a
typeof check to branch between numeric (Unix timestamp * 1000) and string
(direct ISO 8601 parse) paths. fmtFinished() and timeline rendering both
use this helper.

## Key Files

- **langgraph_pipeline/web/static/dashboard.js** - Contains finishedAtToMs()
  helper and fmtFinished() that uses it

## Design Decision

Handle both types at the UI boundary via finishedAtToMs() rather than
normalizing at the backend. This is the simplest approach: a typeof check
branches between numeric and string parsing.

## Validation Task

Since this was previously implemented, the plan task validates that the fix
works correctly for both backends and that no regressions exist.
