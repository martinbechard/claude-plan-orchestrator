# Design: Trace Link Returns 404 Instead of Displaying Trace

Source: tmp/plans/.claimed/01-during-the-execution-of-a-work-item-there-is-a-view-trace-link-in-the-workitem.md
Requirements: docs/plans/2026-04-02-01-during-the-execution-of-a-work-item-there-is-a-view-trace-link-in-the-workitem-requirements.md

## Architecture Overview

The frontend (dashboard.js, item.html) generates "View Trace" links pointing to
/proxy?trace_id={run_id}. However, no GET /proxy endpoint exists in the backend.
The actual trace viewing page is served at /execution-history/{run_id}.

The fix is a single backend route that accepts GET /proxy?trace_id=X and redirects
(HTTP 302) to /execution-history/X. This is the minimal, correct fix that connects
the existing frontend links to the existing trace viewer without touching any
frontend code or modifying the trace viewing infrastructure.

## Key Files

- langgraph_pipeline/web/server.py -- add GET /proxy redirect endpoint
- tests/langgraph/web/test_proxy_redirect.py -- test the new endpoint

## Design Decisions

### D1: Add GET /proxy redirect endpoint in server.py
Addresses: P1, UC1
Satisfies: AC1, AC2, AC3
Approach: Add a GET /proxy route in create_app() that reads the trace_id query
parameter and returns a RedirectResponse(302) to /execution-history/{trace_id}.
If trace_id is missing, return a 400 error. This connects the existing frontend
links to the existing execution history page without modifying any frontend code.
Files: langgraph_pipeline/web/server.py

### D2: Validate trace_id exists before redirecting
Addresses: P1, UC1
Satisfies: AC1, AC2, AC4, AC5
Approach: Before redirecting, call proxy.get_run(trace_id) to verify the trace
exists in the local database. If not found, return a user-friendly HTML error
page (or a 404 with a meaningful message) instead of silently redirecting to
another 404 page. This ensures the user sees actionable feedback.
Files: langgraph_pipeline/web/server.py

### D3: Unit tests for the proxy redirect
Addresses: P1
Satisfies: AC1, AC2
Approach: Add tests covering: (1) valid trace_id redirects to /execution-history/{id},
(2) missing trace_id returns 400, (3) unknown trace_id returns 404 with message.
Use FastAPI TestClient against the app.
Files: tests/langgraph/web/test_proxy_redirect.py

## Design -> AC Traceability Grid

| AC | Design Decision(s) | Approach |
|---|---|---|
| AC1 (non-404 response) | D1, D2 | GET /proxy redirects to execution-history when trace exists |
| AC2 (no JSON error) | D1, D2, D3 | Redirect serves HTML page, not raw JSON; tested |
| AC3 (rendered web page) | D1 | Redirect leads to the existing execution-history HTML page |
| AC4 (correct trace data) | D2 | Validates trace_id maps to a real trace before redirecting |
| AC5 (specific trace ID works) | D2 | Same validation path works for any trace_id including the reported one |
