# Traces page: all runs named "LangGraph" with slug "LangGraph"

## Status: Open

## Priority: Medium

## Summary

Every root trace in the LangSmith proxy is named "LangGraph" and the slug
column also shows "LangGraph". This makes the traces list completely
unreadable — there is no way to tell which run corresponds to which work item.

## Observed Behavior

- Every row in the traces table shows name="LangGraph" and slug="LangGraph".
- Filtering by slug returns no useful results.

## Root Cause

The LangGraph SDK names root runs "LangGraph" by default. The `item_slug` field
is only present in child run metadata (`metadata_json`), not in root run metadata.
The supervisor dispatches workers without injecting the slug into the root run name.

## Expected Behavior

Each trace row should display the actual work item slug (e.g.,
"03-cost-analysis-db-backend") so the user can identify runs at a glance.

## Suggested Fix

When the supervisor dispatches a worker, pass a `run_name` or set the LangGraph
`recursion_limit` config with `run_name=<item_slug>` so the SDK uses that as the
root run name. Alternatively, after the root run is created, update the `name`
column in the local SQLite `traces` table using the `item_slug` from the first
child run that arrives with metadata containing `item_slug`.
