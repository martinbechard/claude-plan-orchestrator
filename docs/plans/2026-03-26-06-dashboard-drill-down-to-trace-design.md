# Design: Dashboard Drill-Down to Trace (06)

## Source
Defect: .claude/plans/.claimed/06-dashboard-drill-down-to-trace.md

## Problem

Active Workers and Recent Completions panels have no link to the Traces page.
Users cannot navigate from a worker or completion directly to its LangSmith
trace detail filtered by trace_id.

## Architecture Overview

Each work item stores its LangSmith trace UUID in the claimed item markdown
file as `## LangSmith Trace: <uuid>`. The worker creates this marker on first
run and re-uses the same UUID across restarts.

The fix threads that UUID from the claimed file through:
1. WorkerInfo (in-memory active workers)
2. CompletionRecord and the completions SQLite table
3. The SSE snapshot payload and list_completions() return value
4. Dashboard HTML/JS rendering (anchor tag per row)

## Key Files

### Backend

| File | Change |
|------|--------|
| `langgraph_pipeline/shared/langsmith.py` | Expose `read_trace_id_from_file(path)` as a public function |
| `langgraph_pipeline/web/dashboard_state.py` | Add `run_id: Optional[str]` to WorkerInfo; update add_active_worker signature and snapshot |
| `langgraph_pipeline/web/proxy.py` | Add `run_id TEXT` column to completions table (ALTER TABLE + schema); update record_completion and list_completions |
| `langgraph_pipeline/supervisor.py` | Read trace_id from claimed file at dispatch and at reap time; pass run_id through |

### Frontend

| File | Change |
|------|--------|
| `langgraph_pipeline/web/templates/dashboard.html` | Add `<a class="trace-link">` element to worker card and completion row templates |
| `langgraph_pipeline/web/static/dashboard.js` | Set href and show/hide trace link in renderWorkers and renderCompletions |

## Design Decisions

**Trace ID at dispatch time**: The supervisor calls `read_trace_id_from_file(claimed_path)` immediately after claiming an item. If the item has never been run before, this returns None and the active worker row shows no link. When the worker writes the UUID, the supervisor re-reads it at reap time and stores it on the completion record.

**Trace ID at reap time**: After the worker exits, the supervisor calls `read_trace_id_from_file(claimed_path)` again to capture the UUID (now guaranteed to be written). This is passed to `record_completion()` so completions always carry the trace link.

**DB migration**: The completions table gains a nullable `run_id TEXT` column. An ALTER TABLE guard (`SELECT * FROM pragma_table_info`) runs at proxy init to add the column to existing databases without dropping data.

**Graceful degradation**: If run_id is None or empty, the JS renders no link — the slug text is shown as plain text. This handles the case where tracing is disabled or not yet initialised.

**URL format**: `/proxy?trace_id=<uuid>` — this depends on defect-05 adding the trace_id filter to the /proxy page. The link is rendered regardless; if filter support is not yet live, the user lands on the unfiltered list.
