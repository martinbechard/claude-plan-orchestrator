# Design: Traces list trace_id column and filter

## Status: Review Required

This feature was previously implemented and needs verification against the
acceptance criteria in the work item.

## Architecture Overview

The trace_id feature spans three layers:

1. **Template** (proxy_list.html) - Trace ID column with truncated display,
   monospace styling, copy-to-clipboard button, and a filter input in the
   filter bar.
2. **Route** (routes/proxy.py) - GET /proxy endpoint accepts trace_id query
   parameter and passes it through to the proxy methods.
3. **Data layer** (proxy.py) - TracingProxy.list_runs() and count_runs()
   accept a trace_id parameter and apply SQL filtering (exact match on
   run_id or parent_run_id).

## Key Files

- langgraph_pipeline/web/templates/proxy_list.html
- langgraph_pipeline/web/routes/proxy.py
- langgraph_pipeline/web/proxy.py

## Design Decisions

- Trace ID is truncated to first 8 characters in the table column for
  readability; the full ID is available via hover (title attribute) and
  copy button.
- The filter matches exact trace UUID, returning both the root run and its
  direct children when a trace_id is specified.
- No separate grouping by thread_id is implemented (listed as optional in
  the work item).

## Verification Scope

The validator should confirm:
1. Trace ID column renders with monospace truncated ID and copy button.
2. Filter input accepts a trace_id and narrows the list.
3. Backend list_runs/count_runs correctly filter by trace_id parameter.
