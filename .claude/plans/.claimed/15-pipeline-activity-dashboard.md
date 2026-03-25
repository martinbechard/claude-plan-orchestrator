# Pipeline activity dashboard

## Status: Open

## Priority: High

## Depends On: Feature 13 (embedded web server)

## Summary

A live-updating dashboard at `/dashboard` showing current pipeline state:
active workers, items being processed, recent completions, running cost,
and error summary. Uses server-sent events (SSE) for live updates — no
WebSocket complexity, no polling from the browser.

## Motivation

The current experience is a terminal scrolling with interleaved worker output
and supervisor heartbeat lines. With multiple concurrent workers it becomes
unreadable. The dashboard gives a single clean view of the whole system.

## Requirements

### State Feed

1. The supervisor loop emits structured state snapshots to an in-process
   `DashboardState` singleton: active workers (PID, item slug, type, elapsed
   time, estimated cost so far), recent completions (last 20, with outcome
   and cost), cumulative session cost, and any errors.

2. `DashboardState` is updated atomically (lock-protected) from the supervisor
   loop thread. It is read by the SSE endpoint.

### SSE Endpoint

3. `GET /api/stream` — Server-Sent Events endpoint. Sends a `state` event
   every 2 seconds (or on change) as a JSON payload. The browser receives
   it and re-renders the relevant DOM sections via vanilla JS `<template>`
   stamping — no React/Vue.

### Dashboard UI (`/dashboard`)

4. **Active workers panel**: one card per worker — item slug (linked to plan
   YAML if it exists), item type badge (defect/feature/analysis colour-coded),
   elapsed time, model tier, live "~$X.XXXX" cost ticker.

5. **Queue panel**: items in the backlog waiting to be picked up (scanned
   from backlog dirs on each SSE tick).

6. **Recent completions panel**: last 20 items with success/warn/fail badge,
   cost, duration. Colour-coded by outcome.

7. **Session summary bar** (pinned at top): total items processed, total cost,
   active worker count, time since supervisor start.

8. **Error stream**: collapsible panel showing recent error log entries from
   workers (parsed from the result JSON `message` field on failure).

### Design constraints

- No build step: vanilla HTML + CSS + minimal JS in `<script>` tags or
  a single `dashboard.js` file served as static.
- Works in a plain browser tab without any extension or login.
- Responsive enough to be readable on a laptop at half-screen width.

## Files

- `langgraph_pipeline/web/dashboard_state.py` — `DashboardState` singleton
- `langgraph_pipeline/web/routes/dashboard.py` — FastAPI router
- `langgraph_pipeline/web/templates/dashboard.html`
- `langgraph_pipeline/web/static/dashboard.js`
- Update `langgraph_pipeline/supervisor.py` — feed `DashboardState` from dispatch loop
- `tests/langgraph/web/test_dashboard_state.py`

## LangSmith Trace: c75950af-fa68-4c8e-858b-953e05fa8d00
