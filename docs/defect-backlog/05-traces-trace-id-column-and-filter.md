# Traces list: add trace_id column, grouping, and filter by trace_id

## Status: Open

## Priority: Medium

## Summary

The traces list has no trace_id (run_id) column and no way to filter or group
by trace_id. Users need to be able to identify specific traces by ID, copy the
ID for correlation, and filter the list to a single trace.

## Observed Behavior

- The trace list shows name, created_at, duration, cost — but not the run_id.
- There is no trace_id filter input on the list page.
- There is no way to group runs by a shared trace session.

## Expected Behavior

- A truncated/copyable trace_id column appears in the traces table.
- A filter input accepts a trace_id (or prefix) to narrow the list to
  matching runs.
- Optionally: runs that share the same thread_id (from metadata_json) are
  visually grouped.

## Suggested Fix

1. Add trace_id column to proxy_list.html table (truncated, monospace, with
   a copy-to-clipboard button or title= showing the full ID).
2. Add a trace_id query parameter to the GET /proxy endpoint and pass it to
   TracingProxy.list_runs() / count_runs() with a "run_id LIKE ?" or
   "run_id = ?" filter.
3. Add a trace_id text input to the filter form in proxy_list.html.
