# Work item detail: traces table shows duplicate entries for same item

## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


## Status: Open

## Priority: Medium

## Summary

The traces table on the work item detail page (/item/<slug>) shows the same
item appearing twice with slightly different timestamps and the same truncated
run ID prefix. For example, 06-work-item-detail-page shows two rows both
starting with "019d28b2..." but with different created_at times (06:08 and
05:51).

## Investigation Needed

1. Query the traces DB for this slug to determine if there are genuinely two
   root runs or if the query is returning child runs alongside root runs:
     SELECT run_id, parent_run_id, name, created_at
     FROM traces WHERE name LIKE '%06-work-item-detail-page%'
     ORDER BY created_at;

2. Check if the item route's trace query is filtering on parent_run_id IS NULL
   (root runs only) or if it also picks up child runs that have the slug in
   their name or metadata.

3. Check if the pipeline actually dispatched two separate workers for the same
   item (retry after failure, or duplicate claim).

## Likely Root Cause

Either:
- The query matches both a root run (renamed per defect 02 fix) and a child
  run that has the slug in its metadata — missing parent_run_id IS NULL filter.
- The pipeline genuinely processed the item twice (dispatched two workers),
  which would be a supervisor bug.
- The route uses name LIKE '%slug%' which matches both the root run and a
  child run that happens to contain the slug string.

## Fix

Once investigated, either:
- Add parent_run_id IS NULL to the trace query on the item detail page.
- Deduplicate by run_id in the route before passing to the template.
- If a genuine double-dispatch, file a separate supervisor defect.

## LangSmith Trace: 5ac5eef7-581a-4748-8919-ad1b69995bfc


## 5 Whys Analysis

**Title:** Trace display semantics undefined for hierarchical execution model

**Clarity:** 4/5 (Well-specified problem with investigation steps; missing only confirmation of root cause)

**5 Whys:**

1. **Why are duplicate traces appearing on the work item detail page?**
   - The traces query is returning multiple run records (both parent and child) for the same work item without filtering to show only the intended run level.

2. **Why does the query return both parent and child runs instead of deduplicating?**
   - Because the route query doesn't filter on `parent_run_id IS NULL`, or uses name-based matching that captures both root and child runs that happen to share the slug.

3. **Why wasn't the hierarchy filter included in the route?**
   - Because the data model contract for runs (parent/child relationships in LangGraph) wasn't fully considered during initial implementation, or the naming convention changed after the route was written without the route being updated.

4. **Why wasn't the parent-child relationship in the execution model accounted for upfront?**
   - Because there's no documented specification defining which run level(s) the UI should display—root orchestrator runs only, worker child runs only, or both.

5. **Why is there no specification for which runs users should see?**
   - Because the LangGraph hierarchical execution model (orchestrator dispatching workers) wasn't translated into explicit UI requirements during design.

**Root Need:** Establish and document a clear contract for trace display: define whether item detail pages should show root runs only, child runs only, or both, and ensure all trace queries consistently implement this contract.

**Summary:** Duplicates result from ambiguous run hierarchy semantics in a multi-level execution model.
