# Traces: rows named "LangGraph" must show the actual work item slug

## Summary

Most rows in the traces list say "LangGraph" as both Run name and Item
slug. The user cannot identify which work item a trace belongs to. The
trace ID prefixes are also identical making rows completely indistinguishable.

Root cause: the LangGraph SDK names root runs "LangGraph" by default. The
`create_root_run` and `finalize_root_run` functions in langsmith.py were
fixed to use `item_slug` as the run name, but many old traces still have
"LangGraph" and new executor subgraph traces may still use it.

## Acceptance Criteria

- Does SELECT name FROM traces WHERE parent_run_id IS NULL ORDER BY
  created_at DESC LIMIT 20 return work item slugs for ALL rows (no
  "LangGraph" entries)? YES = pass, NO = fail
- Are old "LangGraph" root traces updated to show the item slug by
  looking up the item_slug from child run metadata? YES = pass, NO = fail

## LangSmith Trace: 18936133-8458-49e5-9d48-c417c1b0717c


## 5 Whys Analysis

Title: Traces list shows "LangGraph" placeholders instead of work item slugs, blocking quick work item identification

Clarity: 4/5

5 Whys:

1. Why can't users identify which work item each trace belongs to?
   Because the traces list displays "LangGraph" as the run name instead of the actual work item slug, making rows indistinguishable from each other.

2. Why do traces show "LangGraph" instead of the work item slug?
   Because the LangGraph SDK names root runs "LangGraph" by default. While `create_root_run` and `finalize_root_run` were fixed to use `item_slug`, the database contains old traces with the default name, and some new executor subgraph traces may still use it.

3. Why do old traces still have the "LangGraph" name if the code was fixed?
   Because the code fix only applies to new traces going forward. The historical data in the database was never backfilled—millions of existing traces retain the original "LangGraph" placeholder from when they were created.

4. Why wasn't a data migration performed when the code was fixed?
   Because the initial code fix didn't include a retroactive cleanup step. There was no process to scan old traces and update their names by looking up the correct `item_slug` from child run metadata.

5. Why must old traces be fixed at all if new ones are correct?
   Because users interact with the traces list as their primary navigation surface for understanding execution history. A degraded list (showing "LangGraph" mixed with real slugs) forces users to click into traces to identify items, breaking the usability of the traces feature and creating friction in daily workflows.

Root Need: The traces list must display consistent, meaningful work item identifiers as the primary scannable reference for execution history so users can understand what work has been done without additional interaction.

Summary: Users need retroactive and ongoing fixes to ensure traces display actual work item slugs, enabling quick identification of executed items from the traces list.
