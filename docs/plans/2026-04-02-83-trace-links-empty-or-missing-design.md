# Design: 83 Trace Links Empty Or Missing

Source item: tmp/plans/.claimed/83-trace-links-empty-or-missing.md
Requirements: docs/plans/2026-04-02-83-trace-links-empty-or-missing-requirements.md

## Architecture Overview

The trace link pipeline spans four layers:

1. **Trace ID generation** -- langsmith.py creates a UUID and writes a
   "## LangSmith Trace:" marker line to the item markdown file.
2. **Trace data persistence** -- LangSmith SDK posts RunTree data to a
   LANGCHAIN_ENDPOINT (local proxy when the web server runs). The proxy stores
   rows in its SQLite traces table.
3. **Completion recording** -- supervisor.py reads the trace UUID from the item
   file via read_trace_id_from_file() and passes it to proxy.record_completion().
4. **Frontend rendering** -- completions.html renders the run_id as a link to
   /execution-history/{run_id}. That page is an HTML shell with a
   data-run-id attribute; client-side JS is supposed to fetch
   /api/execution-tree/{run_id} and render the tree.

### Root causes

**P1 (empty trace column):** create_root_run() returns (None, None) when
_tracing_active is False or langsmith is not installed. No UUID is generated,
no marker line is written, and the supervisor stores run_id=NULL in
completions. The template shows a dash instead of a link.

**P2 (trace links lead to empty pages):** Two sub-causes:
  - The execution history page has no client-side JavaScript. The template
    shows "Loading execution tree..." but never fetches or renders anything.
  - Even if JS existed, get_run(run_id) returns None when the run_id has no
    corresponding row in the traces table (the route returns 404). This
    happens when tracing was active enough to generate a UUID but the root
    run was never posted to the local proxy.

## Key Files to Create/Modify

| File | Action |
|------|--------|
| langgraph_pipeline/shared/langsmith.py | Modify create_root_run() |
| langgraph_pipeline/web/proxy.py | Modify record_completion(), _init_db() |
| langgraph_pipeline/web/routes/execution_history.py | Modify to pass completion data as fallback |
| langgraph_pipeline/web/templates/execution_history.html | Modify to add tree-rendering JS and empty-state handling |
| langgraph_pipeline/web/static/execution-history.js | Create: client-side tree fetch and render |
| tests/langgraph/shared/test_langsmith.py | Modify: test always-generate behavior |
| tests/langgraph/web/test_proxy.py | Modify: test synthetic trace row creation |

## Design Decisions

### D1: Always generate and persist a trace UUID

- **Addresses:** P1
- **Satisfies:** AC1, AC5
- **Approach:** Modify create_root_run() so it always generates a UUID and
  writes the marker line to the item file, regardless of _tracing_active or
  langsmith availability. When tracing IS active, continue creating the
  RunTree and posting it. When tracing is NOT active, still generate the UUID
  and write the file marker so the supervisor always has a run_id to store.
  This decouples "having a trace identifier" from "having LangSmith tracing
  enabled."
- **Files:** langgraph_pipeline/shared/langsmith.py

### D2: Ensure a root trace row exists for every completion

- **Addresses:** P2
- **Satisfies:** AC2, AC5
- **Approach:** Modify record_completion() in proxy.py so that when called
  with a non-null run_id, it checks whether a trace row exists for that
  run_id. If not, it inserts a synthetic root trace row with the slug as
  name, the completion timestamp as created_at/start_time/end_time, and
  outcome/cost metadata. This guarantees that /execution-history/{run_id}
  never returns 404 for a completion that has a run_id.
- **Files:** langgraph_pipeline/web/proxy.py

### D3: Backfill NULL run_ids in existing completions

- **Addresses:** P1
- **Satisfies:** AC1
- **Approach:** Add a migration step in _init_db() that finds all completions
  rows with NULL run_id, generates a UUID for each, updates the completion
  row, and inserts a synthetic root trace row. This ensures historical
  completions also have trace links. The migration is idempotent (only
  targets NULL run_id rows) and runs at startup.
- **Files:** langgraph_pipeline/web/proxy.py

### D4: Implement client-side execution tree rendering

- **Addresses:** P2, UC1
- **Satisfies:** AC2, AC3, AC4, AC5
- **Approach:** This is the core missing piece. The execution history page is
  an empty HTML shell with no JavaScript. Create execution-history.js that:
  (a) reads the run_id from the data-run-id attribute,
  (b) fetches /api/execution-tree/{run_id},
  (c) renders the tree as a nested collapsible hierarchy with step name,
      status badge, duration, cost, and token count for each node,
  (d) handles the empty-tree case by showing root run info (name, status,
      duration) from the trace row data passed via template context.
  Update execution_history.html to include the script tag and pass initial
  run data to the JS via a data attribute or inline JSON.
  Update execution_history.py route to pass completion/run context data
  that the template can embed for the empty-tree fallback.
- **Files:** langgraph_pipeline/web/static/execution-history.js (new),
  langgraph_pipeline/web/templates/execution_history.html,
  langgraph_pipeline/web/routes/execution_history.py

## Design -> AC Traceability Grid

| AC | Design Decision(s) | Approach |
|----|-------------------|----------|
| AC1 | D1, D3 | Always generate UUID in create_root_run(); backfill NULL run_ids at startup |
| AC2 | D2, D4 | Synthetic trace row prevents 404; JS renders tree content on the page |
| AC3 | D4 | JS fetches tree from API and renders in the page shell; link already navigates correctly |
| AC4 | D4 | JS renders nested collapsible tree showing parent/child hierarchy |
| AC5 | D1, D2, D4 | UUID always generated (valid LangSmith format); synthetic trace row ensures lookup works; JS renders trace data |
| AC6 | D1, D2 | UUID is valid LangSmith format (D1); synthetic trace row ensures the ID resolves to data (D2) |
