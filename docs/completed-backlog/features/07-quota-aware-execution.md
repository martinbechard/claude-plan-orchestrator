# Quota-Aware Execution with Weekly Budget Limits

## Status: Open

## Priority: Medium

## Summary

Add awareness of the user's weekly Claude usage quota to the orchestrator and auto-pipeline,
allowing them to stop or pause before exhausting the user's remaining allowance. Users can
configure a maximum percentage of their weekly quota that automated execution is allowed to
consume (e.g., 90%), reserving the rest for interactive use.

## Problem

The orchestrator and auto-pipeline can run many tasks in sequence, each consuming tokens
from the user's weekly quota (Claude Max/Pro plans have weekly limits). There is currently
no mechanism to:
- Check how much of the weekly quota remains before starting a task
- Stop execution when remaining quota drops below a threshold
- Reserve a portion of the quota for interactive (non-automated) use

This means an overnight auto-pipeline run could exhaust the entire weekly allowance,
leaving no quota for manual work the next day.

## Proposed Design

### 1. Quota Query Mechanism

Investigate how to determine remaining weekly quota. Potential approaches:

a) CLI output: Check if claude --print outputs quota info in result JSON or stderr.
   The CLI shows "You've hit your limit" when quota is exhausted (orchestrator already
   detects this for rate limiting). There may be headers or fields showing remaining quota.

b) Account API: Check if the Anthropic API or Claude account dashboard exposes a
   quota/usage endpoint that can be queried programmatically.

c) Local JSONL aggregation: Sum token usage from local session files
   (~/.claude/projects/.../*.jsonl) for the current billing week. This requires knowing
   the quota ceiling and billing cycle start date.

d) Heuristic: Use the token usage tracking from feature 06-token-usage-tracking to
   maintain a running session total. Combined with a user-configured budget ceiling,
   this provides approximate quota awareness without needing an API.

### 2. Budget Configuration

Add configuration options (via plan YAML meta, CLI flags, or environment variables):

- max_quota_percent: Maximum percentage of weekly quota to use (default: 90%)
- quota_ceiling_usd: User's weekly quota in USD (needed if no API provides it)
- billing_cycle_start: Day of week the quota resets (e.g., "monday")
- reserved_budget_usd: Alternative to percentage - absolute dollar amount to reserve

Example in plan YAML:
```
meta:
  budget:
    max_quota_percent: 90
    quota_ceiling_usd: 100.00
```

Example via CLI:
```
python scripts/plan-orchestrator.py --plan plan.yaml --max-budget-pct 90
```

Note: Claude CLI already supports --max-budget-usd for per-session limits. This feature
adds plan-level and weekly-level awareness on top of that.

### 3. Pre-Task Quota Check

Before each task, the orchestrator should:
1. Calculate total cost spent so far (from token usage tracking feature)
2. Estimate remaining quota (ceiling minus spent this week)
3. If remaining quota is below the reserved threshold, stop gracefully
4. Print a clear message: "Stopping: weekly quota usage at 91% (configured max: 90%)"

### 4. Auto-Pipeline Integration

The auto-pipeline should:
- Check quota before starting each new work item (not just each task)
- A work item involves a design phase + full orchestrator plan execution
- If quota is too low to likely complete a work item, skip it and stop
- Log the reason for stopping in the session report

### 5. Graceful Stop Behavior

When the quota limit is reached:
- Complete the current task (don't interrupt mid-execution)
- Mark the plan as "paused_quota" rather than "completed" or "failed"
- Write the usage report with the pause reason
- Auto-pipeline moves to the next cycle or stops if --once mode

### 6. Quota Estimation (Nice to Have)

If historical usage data is available from previous runs:
- Estimate average cost per task type
- Before starting a plan, estimate total plan cost based on task count
- Warn if estimated plan cost exceeds remaining quota
- "This plan has 12 tasks, estimated cost ~$3.50, remaining quota ~$8.20"

## Research Needed

The main unknown is how to determine the user's remaining weekly quota. This requires
investigating:
- Whether Claude CLI or API exposes remaining quota
- Whether the "You've hit your limit" message includes quota details
- Whether billing/usage endpoints exist for programmatic access
- Whether local JSONL file analysis can approximate weekly usage

If no programmatic quota query exists, the fallback is user-configured budget ceilings
combined with session-level cost tracking.

## Files Likely Affected

| File | Change |
|------|--------|
| scripts/plan-orchestrator.py | Pre-task quota check, budget config parsing, graceful pause |
| scripts/auto-pipeline.py | Per-work-item quota check, session budget tracking |
| Plan YAML schema | meta.budget configuration block |

## Dependencies

- 06-token-usage-tracking.md: Requires per-task cost tracking to calculate running totals.
  This feature builds directly on the usage data collected by the tracking feature.
