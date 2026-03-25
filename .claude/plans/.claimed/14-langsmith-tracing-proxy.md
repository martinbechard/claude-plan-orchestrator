# LangSmith tracing proxy

## Status: Open

## Priority: Medium

## Depends On: Feature 13 (embedded web server)

## Summary

Intercept all LangSmith SDK calls made by the orchestrator, store them in a
local SQLite database, and forward them to the real LangSmith API. Serve a
read-only traces UI at `/proxy` showing the locally-stored traces. This gives
full observability even when LangSmith is unavailable, and provides the raw
data for feature 16 (cost analysis UI).

## Motivation

LangSmith traces are currently fire-and-forget — if the API is down or the
key is missing, traces are silently dropped. The proxy adds local persistence
and a UI without requiring LangSmith credentials.

## Requirements

### Proxy Intercept

1. Replace the direct `langsmith` SDK calls in `langgraph_pipeline/shared/langsmith.py`
   with calls to a `TracingProxy` class. When web is disabled or proxy is
   disabled, `TracingProxy` delegates directly to the existing SDK logic
   (no behaviour change).

2. When proxy is enabled, `TracingProxy`:
   - Writes the trace event to a local SQLite DB
     (`~/.claude/orchestrator-traces.db` or configurable path).
   - Forwards to the real LangSmith API asynchronously (best-effort — failures
     are logged but do not block the caller).

3. Local DB schema (one table per event type is fine; start simple):
   - `traces(id, run_id, parent_run_id, name, start_time, end_time, inputs_json,
     outputs_json, metadata_json, error, created_at)`

### Proxy UI (`/proxy`)

4. Paginated list of recent traces (most recent first), showing:
   - Run name, item slug, start time, duration, total cost, model
   - Status indicator (success / error)
   - Expandable row with full metadata JSON and child runs

5. Filter by: item slug, model, date range.

6. Individual trace view at `/proxy/<run_id>`: timeline of child runs
   (tool calls) with durations shown as a Gantt-style bar chart using
   plain SVG (no JS framework required).

### Configuration

- `web.proxy.enabled: true` in orchestrator-config.yaml (requires web.enabled)
- `web.proxy.db_path: ~/.claude/orchestrator-traces.db`
- `web.proxy.forward_to_langsmith: true` (set false to store-only, no forwarding)

## Files

- `langgraph_pipeline/web/proxy.py` — `TracingProxy`, local DB writer, async forwarder
- `langgraph_pipeline/web/routes/proxy.py` — FastAPI router for `/proxy` endpoints
- `langgraph_pipeline/web/templates/proxy_list.html`
- `langgraph_pipeline/web/templates/proxy_trace.html`
- Update `langgraph_pipeline/shared/langsmith.py` — use `TracingProxy`
- `tests/langgraph/web/test_proxy.py`

## LangSmith Trace: 66a6aeda-53ae-4d9d-b5d7-1fca15effb2e
