# Test: Traceability Validation Pipeline

The dashboard traces page shows "LangGraph" as the item name for most rows
instead of the actual work item slug. The first 4 rows all say "LangGraph"
as both the Run name and Item slug columns.

The trace ID prefix is identical ("019d329a") for many unrelated items,
making it hard to distinguish them.

Users should be able to identify which work item a trace belongs to by
looking at the traces page. The LangGraph SDK names root runs "LangGraph"
by default, which was fixed in create_root_run/finalize_root_run to use
item_slug instead, but many old traces still show the default name.

Executor subgraph traces may also lack item names in their metadata.

The old traces should be backfilled by looking up item_slug from child
span metadata.

## LangSmith Trace: a0814c9c-ee98-4ed5-be02-c863178e96bc
