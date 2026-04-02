# Design: Trace link returns 404 during work item execution

Source: tmp/plans/.claimed/01-during-the-execution-of-a-work-item-there-is-a-view-trace-link-in-the-workitem.md
Requirements: docs/plans/2026-04-02-01-during-the-execution-of-a-work-item-there-is-a-view-trace-link-in-the-workitem-requirements.md

## Architecture Overview

The "View trace" link on the work item detail page (item.html) navigates to
/proxy?trace_id={run_id}. The GET /proxy endpoint in server.py validates the
trace exists in the local SQLite proxy DB via proxy.get_run(trace_id), then
returns a 302 redirect to /execution-history/{run_id}. That page also calls
proxy.get_run(run_id) and returns 404 if not found.

Root cause: during execution, the trace UUID is written to the item markdown
file immediately by create_root_run() in langsmith.py, and the supervisor
polls this file to populate active_worker.run_id for the template. However,
the actual trace data only reaches the proxy DB via run_tree.post() -- which
may be delayed (worker still initializing), may fail silently, or may never
fire if tracing is inactive. Both the /proxy endpoint (server.py:422-427) and
the /execution-history page (execution_history.py:68-70) independently return
404 when the trace is absent from the proxy DB.

The fix removes the strict 404 gates so the user always reaches a useful page.
When trace data is not yet available locally, the execution-history page shows
a "trace in progress" state with an auto-refresh mechanism and an optional
direct LangSmith link.

## Key Files to Modify

- langgraph_pipeline/web/server.py (proxy_redirect endpoint, lines 398-429)
- langgraph_pipeline/web/routes/execution_history.py (page + API endpoints)
- langgraph_pipeline/web/templates/execution_history.html (in-progress fallback UI)
- tests/langgraph/web/test_proxy_redirect.py (update existing tests)

## Design Decisions

### D1: Remove 404 gate from /proxy redirect endpoint
Addresses: P1, FR1
Satisfies: AC2, AC3, AC6, AC9
Approach: Change the /proxy endpoint to always redirect to /execution-history/{trace_id}
when a valid trace_id parameter is provided, regardless of whether the trace exists
in the proxy DB. Remove the proxy.get_run() check and the HTTPException(404) block.
The execution-history page becomes the single point of truth for what content to
display. The existing 400 validation for missing trace_id is retained.
Files: langgraph_pipeline/web/server.py, tests/langgraph/web/test_proxy_redirect.py

### D2: Execution-history page graceful fallback for missing traces
Addresses: P1, P2, UC1, FR1
Satisfies: AC1, AC2, AC3, AC5, AC8, AC10, AC11
Approach: In execution_history_page(), when proxy.get_run() returns None, render the
page in a "trace pending" mode instead of returning 404. Pass trace_found=False
and run_id to the template context. In execution_tree_api(), return an empty tree
with a "pending" status field and the run_id instead of returning 404. The template
detects the pending state and shows a "Trace data is being collected" message with
a meta-refresh or JS auto-refresh (every 5 seconds) so the page updates once data
arrives.
Files: langgraph_pipeline/web/routes/execution_history.py,
       langgraph_pipeline/web/templates/execution_history.html

### D3: Direct LangSmith link fallback
Addresses: P2, UC1
Satisfies: AC5, AC8
Approach: When the trace is not in the local DB, the execution-history page shows a
direct link to the trace on LangSmith using the workspace ID and project name from
orchestrator-config.yaml. The link format is:
https://smith.langsmith.com/o/{workspace_id}/projects/p/{project}/runs/{run_id}
If workspace_id or project is not configured, the link is omitted. This provides
immediate access to trace data even when the local proxy has not captured it yet.
Files: langgraph_pipeline/web/routes/execution_history.py,
       langgraph_pipeline/web/templates/execution_history.html

### D4: Preserve existing preconditions (link exists during execution)
Addresses: UC1
Satisfies: AC7
Approach: No change needed. The item.html template already displays the "View trace"
link when active_worker.run_id is present (item.html:1260-1264), and the supervisor
already polls the item file for the trace UUID (supervisor.py:676-681). AC7 is
satisfied by existing code.
Files: (none -- already working)

## Design -> AC Traceability Grid

| AC | Design Decision(s) | Approach |
|---|---|---|
| AC1 | D2 | Execution-history page renders in "pending" mode instead of 404 |
| AC2 | D1, D2 | Both 404 gates removed; user always reaches a page |
| AC3 | D1, D2 | Backend no longer returns 404 for valid trace UUIDs |
| AC4 | D1, D2 | Can test with trace ID f63374b7-89e4-463d-adc5-4265ab5c9c95 -- redirect works even if not in DB |
| AC5 | D2, D3 | Direct LangSmith link provides access to captured data |
| AC6 | D1, D2 | Frontend link now routes through to a working page |
| AC7 | D4 | Already working -- link displays during execution |
| AC8 | D2, D3 | User can view trace details via LangSmith link or local page once data arrives |
| AC9 | D1 | Frontend URL /proxy?trace_id=X always resolves to a redirect |
| AC10 | D2 | Backend endpoint returns content (page or pending state) for all trace IDs |
| AC11 | D1, D2 | End-to-end flow completes without errors |
