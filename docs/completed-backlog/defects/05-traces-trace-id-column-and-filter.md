# Traces list: add trace_id column, grouping, and filter by trace_id

## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


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




## 5 Whys Analysis

Title: Traces list lacks trace_id visibility and filterability for cross-platform correlation

Clarity: 4

5 Whys:
1. Why does the traces list not display trace_id? — Because the proxy_list.html table design includes only summary metrics (name, created_at, duration, cost), and trace_id was never identified as a necessary display column.

2. Why does the user need to see and filter by trace_id? — Because trace_id is the unique identifier for a specific execution run, and users need it to reference, search for, and isolate individual traces from a longer list.

3. Why do users need to isolate and reference specific traces? — Because they need to investigate execution issues by looking up additional context, logs, and performance metrics associated with that particular trace in the upstream observability system (LangSmith).

4. Why can't users find that context within this dashboard? — Because this dashboard provides a high-level summary view of traces with filtered metrics, not a comprehensive execution log viewer; the detailed investigation tools live in the upstream tracing backend.

5. Why wasn't trace_id surfaced as a first-class feature if it's needed for investigation? — Because the original design treated the dashboard as a standalone summary interface, not anticipating that users would need an easy pivot point to jump to external systems for deeper forensics.

Root Need: Users need an accessible, primary identifier to bridge between this summary dashboard and the upstream observability platform so they can move seamlessly from high-level trace discovery to detailed execution investigation.

Summary: The dashboard creates friction in the user's investigation workflow by hiding the key identifier needed to correlate traces across systems.
