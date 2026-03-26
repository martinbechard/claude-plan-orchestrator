# Pipeline: runaway retry loop when Claude is unresponsive

## Status: Open

## Priority: Critical

## Summary

When Claude is unresponsive (quota exhausted or API error), the pipeline
enters a tight retry loop processing the same items hundreds of times with
zero useful work. Items 04, 07, 09 were each processed 235-241 times in
~16 minutes, with each cycle lasting ~4 seconds and costing $0.00.

## Evidence

    SELECT slug, COUNT(*), SUM(cost_usd)
    FROM completions GROUP BY slug ORDER BY COUNT(*) DESC;

    04-dashboard-scrolling-timeline-view  241 runs  $1.86
    07-completions-paged-table            238 runs  $4.38
    09-verification-notes-in-work-item-page 235 runs  $0.00
    03-cost-analysis-db-backend           121 runs  $4.16

Warn completions at 15:28:32, 15:28:34, 15:28:36... every 2 seconds with
$0.00 cost and ~4 second duration. Claude was not responding.

## Root Causes

1. **No zero-cost circuit breaker**: When a run completes with $0.00 cost
   and "warn" outcome, the pipeline retries immediately with no backoff.
   There is no detection that "Claude is down, stop retrying."

2. **No consecutive-failure backoff**: After N consecutive warns for the
   same item, the pipeline should exponentially back off or park the item.

3. **Verification cycle limit ineffective**: The max_verification_cycles
   limit counts validator cycles within a single run, but the pipeline
   starts fresh runs for the same item. 240 fresh runs each with 1
   cycle = 240 total cycles, bypassing the per-run limit.

4. **No global health check**: The pipeline should check if Claude is
   available before dispatching work (similar to the quota probe loop
   but triggered by recent zero-cost failures, not just explicit quota
   exhaustion signals).

## Expected Behavior

1. After 3 consecutive $0.00 warn completions for any item, pause that
   item with exponential backoff (1m, 5m, 15m, 1h).
2. After 3 consecutive $0.00 warns across ANY items, enter the quota
   probe idle loop — Claude is likely down globally, not just for one item.
3. Cap total completions per item at a configurable max (e.g. 10). After
   that, park the item with a "max retries exceeded" status and notify
   via Slack.
4. Log a dashboard error when entering the backoff/pause state.

## Fix

1. Track consecutive zero-cost warns per item in the supervisor (or in
   the completions DB — query recent completions for the slug).
2. When the threshold is hit, either:
   a. Move the item to a "parked" directory that the scanner ignores
   b. Or enter the quota probe loop before retrying
3. Add a global consecutive-failure counter: if the last N items across
   all types all returned $0.00 warn, enter quota probe.
4. Add a per-item max completions cap with Slack notification.
