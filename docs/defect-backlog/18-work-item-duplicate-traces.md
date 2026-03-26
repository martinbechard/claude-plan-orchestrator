# Work item detail: traces table shows duplicate entries for same item

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
