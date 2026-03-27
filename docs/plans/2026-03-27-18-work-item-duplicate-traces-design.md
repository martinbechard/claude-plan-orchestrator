# Design: Fix Duplicate Traces on Work Item Detail Page

## Problem

The traces table on the work item detail page (/item/<slug>) showed the same
item appearing twice with slightly different timestamps and the same truncated
run ID prefix.

## Current State (Review Required)

Prior implementation added two key fixes to the trace query in
langgraph_pipeline/web/proxy.py (list_root_traces_by_slug):

1. **parent_run_id IS NULL** filter -- excludes child runs, showing only root runs
2. **GROUP BY run_id** with **MIN(created_at)** -- deduplicates rows where the
   same run_id appears multiple times (e.g., start and end trace events)

The SQL query is:
```
SELECT run_id, name, MIN(created_at) AS created_at
FROM traces
WHERE parent_run_id IS NULL AND name LIKE ?
GROUP BY run_id
ORDER BY created_at DESC
```

## Key Files

- langgraph_pipeline/web/proxy.py -- TracingProxy.list_root_traces_by_slug()
  (lines ~609-627)
- langgraph_pipeline/web/routes/item.py -- _load_root_traces() helper and
  item_detail() route handler
- langgraph_pipeline/web/templates/item.html -- traces table rendering

## Task

Verify the existing fix resolves the duplicate traces issue. If any edge cases
remain (e.g., name matching picking up unrelated runs, or the GROUP BY not
covering all duplicate scenarios), fix them.

## Design Decisions

- Root-only display: The item detail page shows only root orchestrator runs
  (parent_run_id IS NULL). Child runs are visible in the trace detail view.
- Deduplication via GROUP BY: Handles the case where the traces table stores
  multiple events per run_id (start/end callbacks).
- Name-based matching via LIKE: Matches slug anywhere in the run name, which
  is the established convention for how runs are named after work items.
