# Design: Trace Link Returns 404 Instead of Displaying Trace

Source: tmp/plans/.claimed/01-during-the-execution-of-a-work-item-there-is-a-view-trace-link-in-the-workitem.md
Requirements: docs/plans/2026-04-02-01-during-the-execution-of-a-work-item-there-is-a-view-trace-link-in-the-workitem-requirements.md

## Architecture Overview

The frontend (item.html templates and JavaScript) generates "View Trace" links
pointing to /proxy?trace_id={run_id}. The actual trace viewing page is served at
/execution-history/{run_id}. The defect is that no GET /proxy endpoint existed in
the backend, so all trace links returned {"detail":"Not Found"}.

The fix adds a single backend route in server.py that accepts GET /proxy?trace_id=X,
validates the trace exists via the local proxy database, and redirects (HTTP 302)
to /execution-history/X. This connects existing frontend links to the existing
trace viewer without modifying any frontend template code or the trace viewing
infrastructure.

UC1 is tagged UI but is satisfied entirely by the backend redirect -- the
execution-history page already renders trace data. No visual design changes needed.

## Key Files

- langgraph_pipeline/web/server.py -- add GET /proxy redirect endpoint
- tests/langgraph/web/test_proxy_redirect.py -- test the new endpoint

## Design Decisions

### D1: Add GET /proxy redirect endpoint in server.py
Addresses: P1, P2, UC1, FR1
Satisfies: AC1, AC2, AC3, AC7, AC9
Approach: Add a GET /proxy route in create_app() that reads the trace_id query
parameter and returns a RedirectResponse(302) to /execution-history/{trace_id}.
If trace_id is missing, return a 400 error. This establishes the working path
from frontend trace links to backend trace retrieval (FR1), ensures the frontend
link URL targets a valid implemented endpoint (AC7), and eliminates the 404 error
(AC2, AC3). The redirect serves the existing execution-history HTML page (AC1).
Files: langgraph_pipeline/web/server.py

### D2: Validate trace_id exists before redirecting
Addresses: P1, P2, UC1
Satisfies: AC1, AC4, AC5, AC6, AC8, AC9
Approach: Before redirecting, call proxy.get_run(trace_id) to verify the trace
exists in the local database. If not found, return a 404 with a user-friendly
message instead of silently redirecting to another 404 page. This validates that
the trace ID embedded in the frontend link correctly maps to a real LangSmith
trace (AC8), ensures LangSmith trace data is accessible during execution (AC5),
unblocks visibility into LangSmith data (AC6), and confirms the backend returns
trace details for valid links (AC9).
Files: langgraph_pipeline/web/server.py

### D3: Unit tests for the proxy redirect
Addresses: P1, FR1
Satisfies: AC2, AC3, AC7, AC9
Approach: Add tests covering: (1) valid trace_id redirects to /execution-history/{id}
with 302 status, (2) missing trace_id returns 400, (3) unknown trace_id returns 404
with descriptive message, (4) endpoint is reachable and responds correctly. Use
FastAPI TestClient against the app.
Files: tests/langgraph/web/test_proxy_redirect.py

## Design -> AC Traceability Grid

| AC | Design Decision(s) | Approach |
|---|---|---|
| AC1 (trace displays when link clicked) | D1, D2 | GET /proxy redirects to execution-history page which renders the trace |
| AC2 (successful HTTP response, no 404) | D1, D3 | Redirect returns 302 for valid traces; tested |
| AC3 (backend resolves without 404) | D1, D3 | GET /proxy endpoint handles requests, returns 302 or meaningful error |
| AC4 (users access traces for behavior) | D2 | Validates trace exists before redirect, ensuring correct data |
| AC5 (LangSmith data accessible during execution) | D2 | Proxy validates trace_id against local LangSmith trace DB |
| AC6 (LangSmith data visibility unblocked) | D2 | Working redirect path connects frontend links to trace viewer |
| AC7 (frontend link targets valid endpoint) | D1, D3 | GET /proxy endpoint is implemented and reachable; tested |
| AC8 (trace ID maps to LangSmith trace) | D2 | proxy.get_run(trace_id) validates ID against LangSmith trace store |
| AC9 (backend returns details for valid links) | D1, D2, D3 | Valid trace_id -> 302 -> execution-history page with trace data; tested |
