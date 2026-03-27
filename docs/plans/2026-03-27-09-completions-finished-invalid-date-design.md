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

## Key Files

- **langgraph_pipeline/web/static/dashboard.js** - Contains fmtFinished() and
  any timestamp conversion helpers

## Fix

Update fmtFinished() (or its helper) to detect the type of finished_at and
construct Date accordingly:
- number: new Date(value * 1000) (Unix seconds to ms)
- string: new Date(value) (ISO 8601 natively parsed)

## Design Decision

Handle both types at the UI boundary rather than normalizing at the backend.
This is the simplest approach: a typeof check branches between numeric and
string parsing.

## Prior Implementation Notes

This item was previously attempted. The work item is marked "Review Required" -
the task should validate existing code first and only fix what is broken.
