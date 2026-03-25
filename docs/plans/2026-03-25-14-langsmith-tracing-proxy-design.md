# LangSmith Tracing Proxy — Design

**Goal:** Intercept all LangSmith SDK calls, persist them in a local SQLite
database, forward them to the real LangSmith API asynchronously, and expose a
read-only traces UI at `/proxy`.

**Architecture:** A `TracingProxy` class in `langgraph_pipeline/web/proxy.py`
wraps every LangSmith emit call that currently exists in `langsmith.py`. When
the proxy is disabled (or the web server is not running), the class delegates
directly to the existing SDK logic with no behaviour change. When enabled, it
writes a normalised row to a local SQLite DB and fires an async best-effort
forward to the real LangSmith API. A FastAPI router at `/proxy` reads from the
same DB and renders paginated/filterable list and detail views using Jinja2
templates that extend the base layout from Feature 13.

**Depends on:** Feature 13 (embedded web server infrastructure) — `langgraph_pipeline/web/`
must exist before any web layer in this feature can be wired up.

**Tech Stack:** Python stdlib `sqlite3`, FastAPI, Jinja2 (both bundled with the
Feature 13 server), plain SVG for Gantt chart (no JS framework).

---

## Key Files

| File | Action | Purpose |
|------|--------|---------|
| `langgraph_pipeline/web/proxy.py` | Create | `TracingProxy`, SQLite init/write, async forwarder, DB read helpers |
| `langgraph_pipeline/web/routes/__init__.py` | Create | Package init |
| `langgraph_pipeline/web/routes/proxy.py` | Create | FastAPI router, `/proxy` + `/proxy/{run_id}` endpoints |
| `langgraph_pipeline/web/templates/proxy_list.html` | Create | Paginated trace list with filters |
| `langgraph_pipeline/web/templates/proxy_trace.html` | Create | Timeline / Gantt detail view |
| `langgraph_pipeline/shared/langsmith.py` | Modify | Route `emit_tool_call_traces` + `create_root_run` + `finalize_root_run` through `TracingProxy` |
| `langgraph_pipeline/web/server.py` | Modify | Mount proxy router when `web.proxy.enabled` is true |
| `.claude/orchestrator-config.yaml` | Modify | Document `web.proxy` config keys (commented by default) |
| `tests/langgraph/web/test_proxy.py` | Create | Unit tests |

---

## Database Schema

Single table; start simple, no normalisation needed:

```sql
CREATE TABLE IF NOT EXISTS traces (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      TEXT NOT NULL,
    parent_run_id TEXT,
    name        TEXT NOT NULL,
    start_time  TEXT,
    end_time    TEXT,
    inputs_json TEXT,
    outputs_json TEXT,
    metadata_json TEXT,
    error       TEXT,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_traces_run_id       ON traces (run_id);
CREATE INDEX IF NOT EXISTS idx_traces_parent_run_id ON traces (parent_run_id);
CREATE INDEX IF NOT EXISTS idx_traces_created_at   ON traces (created_at);
```

---

## Configuration

Extend `web:` block in `orchestrator-config.yaml`:

```yaml
web:
  enabled: true          # required for proxy
  port: 7070
  proxy:
    enabled: true
    db_path: ~/.claude/orchestrator-traces.db
    forward_to_langsmith: true   # false = store-only, no forwarding
```

---

## TracingProxy Design

```python
class TracingProxy:
    """Intercepts LangSmith trace calls for local persistence and forwarding."""

    def __init__(self, config: dict) -> None: ...

    # Called from langsmith.py in place of direct SDK calls
    def record_run(self, run_id, parent_run_id, name, run_type,
                   inputs, outputs, metadata, error, start_time, end_time) -> None:
        """Write to SQLite, then schedule async forward if enabled."""

    # Async forwarder (best-effort, never raises)
    def _forward_async(self, payload: dict) -> None: ...

    # DB read helpers used by the router
    def list_runs(self, page, page_size, slug, model, date_from, date_to) -> list[dict]: ...
    def get_run(self, run_id: str) -> dict | None: ...
    def get_children(self, run_id: str) -> list[dict]: ...
```

A module-level singleton `get_proxy()` returns the shared instance (or a
no-op stub when the proxy is disabled).

---

## API Endpoints

| Route | Template | Description |
|-------|----------|-------------|
| `GET /proxy` | `proxy_list.html` | Paginated list, query params: `page`, `slug`, `model`, `date_from`, `date_to` |
| `GET /proxy/{run_id}` | `proxy_trace.html` | Child run timeline with SVG Gantt |

---

## UI: Trace List

- Table columns: Run name, Item slug, Start time, Duration, Total cost, Model, Status badge
- Filter bar: slug text input, model dropdown, date-from / date-to date pickers
- Pagination controls (previous / next page links)
- Expandable row: full `metadata_json` pretty-printed, child run count

## UI: Trace Detail (`/proxy/{run_id}`)

- Header: run name, start time, total duration, model, status
- SVG Gantt chart: each child run is a horizontal bar proportional to its
  duration; bars are labelled with the tool/run name; no JS required
- JSON section: collapsible inputs / outputs / metadata blocks

---

## Integration with langsmith.py

`emit_tool_call_traces` currently builds a `RunTree` and calls `.post()`. With
the proxy enabled, the same data is first written to SQLite via `TracingProxy`,
then forwarded to LangSmith (if `forward_to_langsmith` is true). When the proxy
is disabled, the existing code path runs unchanged.

The module-level `_tracing_active` flag in `langsmith.py` is unchanged; the
proxy has its own `_proxy_enabled` check.

---

## Testing Strategy

- `test_proxy_db_write_and_read`: write a run via `TracingProxy.record_run()`,
  read it back with `list_runs()` and `get_run()`.
- `test_proxy_list_endpoint`: start a `TestClient`, write a row, call `GET /proxy`,
  assert 200 and row is present in HTML.
- `test_proxy_detail_endpoint`: call `GET /proxy/{run_id}`, assert 200 and Gantt
  SVG is present.
- `test_proxy_disabled_no_db`: when `proxy.enabled` is false, `record_run()`
  is a no-op and no DB file is created.
- `test_proxy_forward_failure_does_not_raise`: simulate an HTTP error in the
  forwarder and verify `record_run()` still returns without exception.
