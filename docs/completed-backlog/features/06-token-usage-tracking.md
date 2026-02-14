# Token Usage Tracking and Cost Reporting

## Status: Open

## Priority: Medium

## Summary

Track token consumption across orchestrator tasks and auto-pipeline work items, producing
per-task and aggregate usage reports. This gives visibility into how much each plan,
section, and individual task costs in tokens and dollars.

## Problem

Currently the orchestrator and auto-pipeline have no visibility into token consumption.
The only cost data captured is a brief print in verbose mode (line ~1326 of
plan-orchestrator.py) that shows total_cost_usd for each task but does not store it.
There is no aggregation, no per-plan totals, and no per-work-item totals in auto-pipeline.

Without this data:
- Users cannot estimate cost of future plans based on past runs
- Users cannot identify which tasks or work items consume the most tokens
- There is no data to optimize prompt sizes or agent selection
- Cache hit rates are invisible (higher cache hits = lower cost)

## What the Claude CLI Already Provides

The Claude CLI exposes full usage data in its output:

When using --output-format json, the result JSON includes:
- total_cost_usd: authoritative cost for the session
- usage.input_tokens, usage.output_tokens
- usage.cache_read_input_tokens, usage.cache_creation_input_tokens
- modelUsage: per-model breakdown with costUSD per model
- num_turns, duration_ms, duration_api_ms

When using --output-format stream-json (verbose mode), the final result event
contains all the same fields.

Note: There is a known bug (GitHub issue #6805) where stream-json duplicates usage
stats across content blocks. The final result event's total_cost_usd is authoritative
and not affected by this bug.

## Proposed Design

### 1. Extend TaskResult with Usage Data

Add a TaskUsage dataclass to hold per-task token metrics:
- input_tokens, output_tokens
- cache_read_tokens, cache_creation_tokens
- total_cost_usd
- num_turns
- duration_api_ms

TaskResult gets an optional usage field populated after each task completes.

### 2. Always Capture Structured Output

Currently the orchestrator only uses --output-format stream-json in verbose mode.
Change to always use --output-format json (non-verbose) or stream-json (verbose)
so usage data is available in all modes.

In non-verbose mode, parse the final stdout as JSON to extract the result.
In verbose mode, extract the result event from the stream (already parsed at line ~1322).

### 3. Plan-Level Usage Aggregation

Add a PlanUsageTracker that accumulates usage across all tasks in a plan run:
- Per-task usage stored by task_id
- Running totals for input/output/cache tokens and cost
- Cache hit rate calculation: cache_read / (cache_read + input_tokens)
- Print a summary line after each task showing running totals
- Print a final summary when the plan completes

### 4. Usage Report File

Write a usage-report.json alongside the plan YAML after completion:
- Plan name, completion timestamp
- Total cost, total tokens (input, output, cache)
- Cache hit rate
- Per-task breakdown
- Per-section subtotals

### 5. Auto-Pipeline Aggregation

The auto-pipeline should aggregate usage across all work items processed in a session:
- Per-work-item totals (design phase + orchestrator execution phase)
- Session-level grand total
- Write a session usage report when the pipeline stops

### 6. Log File Enhancement

The existing per-task log files (.claude/plans/logs/task-*.log) should include the
parsed usage data in their header section alongside the existing duration and return code.

## Files Likely Affected

| File | Change |
|------|--------|
| scripts/plan-orchestrator.py | TaskUsage dataclass, parse CLI output, PlanUsageTracker, report generation |
| scripts/auto-pipeline.py | Aggregate orchestrator usage per work item, session report |

## Implementation Notes

- The key code change in run_claude_task() is small: parse the result JSON and populate TaskUsage
- In verbose mode, stream_json_output() already parses the result event; store its fields instead of just printing
- In non-verbose mode, add --output-format json and json.loads(stdout) after process completes
- Parallel tasks: each subagent returns its own usage; merge after worktree tasks complete
- Cost display: use total_cost_usd from the CLI (authoritative), do not calculate from token counts

## Dependencies

None - this is a standalone enhancement to existing infrastructure.
