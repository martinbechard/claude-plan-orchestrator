# Pre-compute inclusive cost for trace runs

## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


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

## LangSmith Trace: d9153e64-1e3c-4859-a04e-711b8b1dedd0


## 5 Whys Analysis

Title: Pre-compute inclusive cost for efficient trace cost analysis

Clarity: 4

5 Whys:

1. **Why does the cost analysis page need to show inclusive cost for sorting/filtering?**
   Because users need to identify which trace runs consume the most total resources, including all their sub-calls and descendants, to understand full cost attribution.

2. **Why is identifying high-cost runs important to users?**
   Because understanding cost distribution helps organizations optimize API usage, identify expensive workflows, and make data-driven decisions about what to improve or retire.

3. **Why is the current query-time approach (recursive CTE) creating a bottleneck?**
   Because with 26K+ traces, calculating cumulative costs by walking parent chains on every query/filter/sort operation becomes prohibitively slow (likely exceeds acceptable page load times).

4. **Why does the inclusive cost calculation create such a performance burden?**
   Because inclusive cost requires aggregating an unknown number of descendant costs per trace, and performing this calculation on-demand for every row during interactive operations results in exponential complexity.

5. **Why is this performance issue blocking the product now?**
   Because the system has scaled to production volumes (26K+ traces) where users expect sub-second interactive sorting/filtering by cost metrics as a baseline feature for their cost optimization workflows.

Root Need: Organizations need **fast, interactive cost attribution visibility** across large trace datasets to make timely optimization decisions about API spending—moving from batch-mode analysis to real-time cost insight.

Summary: Without pre-computed inclusive costs, the cost analysis page becomes too slow to use interactively at production scale, blocking users' ability to identify and address expensive workflows.
