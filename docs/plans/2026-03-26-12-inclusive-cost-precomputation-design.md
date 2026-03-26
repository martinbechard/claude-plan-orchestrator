# Design: Pre-compute Inclusive Cost for Trace Runs

Feature: 12-inclusive-cost-precomputation
Date: 2026-03-26

## Architecture Overview

The `/analysis` page currently computes `inclusive_cost_usd` (a run's own cost plus all
descendants' costs) via a correlated recursive CTE inside the main `list_cost_runs` SELECT.
Because the query sorts by `inclusive_cost_usd`, SQLite must evaluate the CTE for every
row in the traces table before it can paginate — O(N) recursive CTEs on 26K+ rows.

The fix implements the backlog's recommended Option 3: limit CTE execution to the current
page only. The query is split into two steps:

1. **Pre-filter pass**: Run the main query with all filters, sort by `exclusive_cost_usd`
   (or `created_at`), and retrieve only the `page_size` run_ids for the current page.
   No recursive CTE at this stage.

2. **Enrichment pass**: For those `page_size` run_ids only, compute `inclusive_cost_usd`
   by running a single recursive CTE that covers all selected roots at once (using an
   `IN (...)` anchor set), then join back to the pre-filtered rows.

3. **Re-sort**: If the caller requested `inclusive_desc` order, re-sort the enriched page
   in Python by `inclusive_cost_usd DESC`. The sort is page-local (best-effort), which
   the backlog explicitly accepts as a con of Option 3.

This reduces recursive CTE work from O(N_total) to O(page_size) per request.

## Key Files

### Modified

- `langgraph_pipeline/web/proxy.py`
  - Replace the correlated-subquery approach in `list_cost_runs()` with the two-pass
    strategy described above.
  - Add a `_compute_inclusive_costs(conn, run_ids)` helper that runs a single
    multi-anchor recursive CTE and returns `{run_id: inclusive_cost_usd}`.
  - Remove the now-unused `_INCLUSIVE_COST_CTE` module constant if confirmed unused
    elsewhere.

## Design Decisions

- **Two-pass instead of pre-computed column**: Avoids schema migration and write
  amplification. Matches the backlog recommendation to start with Option 3.

- **Single multi-anchor CTE**: Rather than N separate CTEs (one per run_id), anchor the
  recursive CTE on all page run_ids at once using `WHERE run_id IN (...)`. SQLite expands
  this correctly and executes one traversal pass, keeping the enrichment fast.

- **Page-local inclusive sort**: When `sort=inclusive_desc`, the pre-filter pass uses
  `exclusive_cost_usd DESC` to get good candidates, then the page is re-sorted by
  inclusive cost. This is approximate but acceptable at current scale per the backlog spec.

- **No template or route changes**: The `inclusive_cost_usd` field already exists on
  `CostRun` and is already rendered in `analysis.html`. Only `proxy.py` changes.
