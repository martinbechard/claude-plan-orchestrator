# Design: Traces Model Filter and Column Fix

## Work Item
`.claude/plans/.claimed/01-traces-model-filter-broken.md`

## Problem

The model filter on `/proxy` returns no results and the model column shows blank. Root cause: LangSmith SDK stores only `thread_id`, `LANGSMITH_WORKSPACE_ID`, and `revision_id` in root run metadata — no model name. The current filter does `metadata_json LIKE '%<model>%'` on root runs, which always misses.

Model information is available in child runs (LLM calls), specifically in `extra.invocation_params.model` or `extra.metadata.ls_model_name`.

## Architecture

### Data Flow

```
LangSmith SDK  →  POST /runs/multipart  →  runs_multipart()  →  proxy.record_run()
                                                                         ↓
                                                              SQLite traces table
```

Child runs (type "llm") carry model info in `extra.invocation_params`. We intercept this in `server.py` and propagate it up to the root run.

### Schema Change

Add a `model TEXT NOT NULL DEFAULT ''` column to the `traces` table. Existing databases need a migration via `ALTER TABLE traces ADD COLUMN model TEXT NOT NULL DEFAULT ''` (with error suppression for the case where the column already exists).

### Model Extraction (server.py)

When processing any run in `runs_multipart` or `runs_create`:

```python
extra = run_data.get("extra") or {}
inv = extra.get("invocation_params") or {}
meta = extra.get("metadata") or {}
model = (
    inv.get("model") or inv.get("model_name") or
    meta.get("ls_model_name") or meta.get("model") or ""
)
```

If `model` is non-empty and the run has a `parent_run_id`, call `proxy.propagate_model_to_root(parent_run_id, model)` to update the root run's model column.

### New Method: propagate_model_to_root()

In `TracingProxy`:

```python
def propagate_model_to_root(self, parent_run_id: str, model: str) -> None
```

Walks up `parent_run_id` chain until `parent_run_id IS NULL`, then sets the `model` column on that root run (only if currently empty, to avoid overwriting with a less-specific value).

### Filter Change (proxy.py)

Replace `metadata_json LIKE ?` with `model LIKE ?` in both `list_runs()` and `count_runs()`. Case-insensitive substring match via `LOWER(model) LIKE LOWER(?)`.

### Display Change (routes/proxy.py)

`_enrich_run()` currently reads model from `metadata_json`. Update to use `run.get("model", "")` directly.

## Key Files

| File | Change |
|---|---|
| `langgraph_pipeline/web/proxy.py` | Add `model` column, migration, `propagate_model_to_root()`, update filter queries |
| `langgraph_pipeline/web/server.py` | Extract model from `extra.invocation_params`, call `propagate_model_to_root()` |
| `langgraph_pipeline/web/routes/proxy.py` | Use `run.get("model")` in `_enrich_run()` |
| `tests/langgraph/web/test_proxy.py` | Add tests for model propagation and filter |

## Design Decisions

1. **Dedicated column over metadata scan**: Filtering on a typed `model` column is reliable and indexable. `metadata_json LIKE` was fragile by design.
2. **Propagate to root only**: Root runs are what the list view shows. Child runs don't need the column populated for display.
3. **First-write wins**: Only update root model when currently empty. The first LLM child encountered sets the model; subsequent children (potentially different models) don't overwrite.
4. **No data migration for old rows**: Old rows will show blank model; that's acceptable. Only new traces get model populated.
5. **ALTER TABLE migration**: Handles existing databases without data loss. SQLite silently errors when a column already exists; we catch `OperationalError` on the ALTER.
