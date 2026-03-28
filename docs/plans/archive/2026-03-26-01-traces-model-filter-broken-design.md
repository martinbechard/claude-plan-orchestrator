# Design: Traces Model Filter Broken and Model Column Missing

## Work Item

`.claude/plans/.claimed/01-traces-model-filter-broken.md`

## Problem

The model filter on the traces page returns no results because model information
was not being stored in trace metadata where the filter queries it. The traces
table also lacked a model column.

## Implementation Status: Review Required

A previous fix implemented the full solution. The task now is to validate that all
acceptance criteria hold and fix any gaps found.

## Architecture

### Data Flow

```
LangSmith SDK  ->  POST /runs/multipart  ->  runs_multipart()  ->  proxy.record_run()
                                                                         |
                                                              SQLite traces table
```

Child runs (type "llm") carry model info in extra.invocation_params. The server
intercepts this and propagates it up to the root run via propagate_model_to_root().

### Schema

Dedicated model TEXT NOT NULL DEFAULT '' column on the traces table with an index.
Migration via ALTER TABLE with error suppression for existing databases.

### Model Extraction (server.py)

When processing any run in runs_multipart or runs_create, model is extracted from:
- extra.invocation_params.model
- extra.invocation_params.model_name
- extra.metadata.ls_model_name
- extra.metadata.model

If model is non-empty and the run has a parent_run_id, propagate_model_to_root()
updates the root run's model column (first-write-wins).

### Filter (proxy.py)

list_runs() and count_runs() filter on LOWER(model) LIKE LOWER(?) against the
dedicated column, not metadata_json.

### Display (routes/proxy.py, templates)

_enrich_run() reads from run.get("model") directly. The template renders
run.display_model in a dedicated Model column. A dropdown filter provides
hardcoded Claude model options.

## Key Files

| File | Role |
|---|---|
| langgraph_pipeline/web/proxy.py | TracingProxy, model column, propagate_model_to_root(), list_runs filter |
| langgraph_pipeline/web/server.py | Model extraction from runs_multipart/runs_create |
| langgraph_pipeline/web/routes/proxy.py | _enrich_run() display_model |
| langgraph_pipeline/web/templates/proxy_list.html | Model column and filter dropdown |
| tests/langgraph/web/test_proxy.py | Tests for propagation, filtering, multipart extraction |

## Design Decisions

1. Dedicated column over metadata scan: Filtering on a typed model column is reliable and indexable
2. Propagate to root only: Root runs are what the list view shows
3. First-write wins: Only update root model when currently empty
4. No data migration for old rows: Old rows show blank model; acceptable
5. ALTER TABLE migration: Handles existing databases without data loss
