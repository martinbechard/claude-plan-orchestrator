# Pre-compute inclusive cost for trace runs

## Status: Open

## Priority: Medium

## Summary

The cost analysis page needs to show inclusive cost (a run's own cost plus
all its descendants' costs) for sorting and filtering. Computing this via
a recursive CTE at query time is expensive on 26K+ traces. A pre-computed
inclusive_cost_usd column or materialized view would make the page fast.

## Options

1. **Column + trigger**: Add inclusive_cost_usd column to traces table.
   On INSERT, walk up the parent chain and update ancestors. Pro: always
   up-to-date. Con: write amplification on every trace insert.

2. **Batch job**: A periodic background task (every 60s or on-demand)
   recomputes inclusive costs for all root runs. Pro: simple, no trigger
   complexity. Con: stale for up to 60s.

3. **Query-time CTE**: No schema change. Use recursive CTE only for the
   current page of results (after filtering/sorting by exclusive cost
   first, then enrich top-N with inclusive cost). Pro: no maintenance.
   Con: slower, limits sorting by inclusive cost.

## Recommendation

Start with option 3 (query-time CTE limited to current page) since the
trace count is manageable. Move to option 2 if performance degrades
beyond 500ms query time.
