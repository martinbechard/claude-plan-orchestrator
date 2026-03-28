# Quota-Aware Execution with Weekly Budget Limits - Design Document

> **For Claude:** REQUIRED SUB-SKILL: Use the implement skill to execute this plan task-by-task.

**Goal:** Add budget awareness to the orchestrator and auto-pipeline so they can stop gracefully before exhausting the user's weekly Claude usage quota, reserving a configurable portion for interactive use.

**Architecture:** Add a BudgetConfig dataclass to hold budget limits parsed from plan YAML meta or CLI flags. Add a BudgetGuard class that checks cumulative cost (from PlanUsageTracker, Feature 06) against the configured ceiling before each task. When spending exceeds the threshold, the orchestrator pauses the plan with a "paused_quota" status. The auto-pipeline performs a per-work-item budget check and stops processing new items when the budget is exhausted. No external quota API is required; the system uses locally-tracked cost data combined with a user-configured ceiling.

**Tech Stack:** Python 3 (plan-orchestrator.py, auto-pipeline.py), YAML (plan meta.budget configuration)

---

## Architecture Overview

### Dependency: Feature 06 (Token Usage Tracking)

This feature builds directly on the TaskUsage dataclass, PlanUsageTracker, and per-task cost data introduced by Feature 06. Specifically:

- TaskResult.usage provides per-task cost via total_cost_usd
- PlanUsageTracker.get_total_usage() provides cumulative plan cost
- Usage report JSON files provide cross-plan session cost data

Feature 06 must be implemented before this feature.

### BudgetConfig Dataclass

New dataclass to hold budget configuration:

    @dataclass
    class BudgetConfig:
        """Budget limits for plan execution."""
        max_quota_percent: float = 100.0  # Max % of ceiling to use (e.g., 90.0)
        quota_ceiling_usd: float = 0.0    # Weekly quota ceiling in USD (0 = unlimited)
        reserved_budget_usd: float = 0.0  # Absolute USD to reserve (alternative to %)

        @property
        def effective_limit_usd(self) -> float:
            """Calculate effective spending limit in USD."""
            if self.quota_ceiling_usd <= 0:
                return float('inf')
            percent_limit = self.quota_ceiling_usd * (self.max_quota_percent / 100.0)
            if self.reserved_budget_usd > 0:
                reserve_limit = self.quota_ceiling_usd - self.reserved_budget_usd
                return min(percent_limit, reserve_limit)
            return percent_limit

Configuration sources (in priority order):
1. CLI flags: --max-budget-pct, --quota-ceiling
2. Plan YAML meta.budget block
3. Defaults (100% / unlimited = no budget enforcement)

### BudgetGuard Class

Stateful guard that tracks cumulative spending and enforces limits:

    class BudgetGuard:
        """Checks cumulative cost against budget limits before each task."""

        def __init__(self, config: BudgetConfig):
            self.config = config
            self.session_cost_usd: float = 0.0

        def record_cost(self, cost_usd: float) -> None:
            """Add cost from a completed task."""
            self.session_cost_usd += cost_usd

        def can_proceed(self) -> tuple[bool, str]:
            """Check if budget allows another task.
            Returns (can_proceed, reason_if_not).
            """

        def get_usage_percent(self) -> float:
            """Current spending as percentage of ceiling."""

        def format_status(self) -> str:
            """Format current budget status for display."""

The guard returns a tuple so the caller gets both the decision and a human-readable explanation.

### Plan YAML Configuration

Budget settings in the plan meta block:

    meta:
      name: My Feature
      budget:
        max_quota_percent: 90
        quota_ceiling_usd: 100.00

When no budget block is present, no budget enforcement occurs (backwards compatible).

### CLI Flags

New orchestrator flags:

    --max-budget-pct N     Maximum % of quota ceiling to use (default: 100)
    --quota-ceiling N.NN   Weekly quota ceiling in USD (default: 0 = unlimited)

CLI flags override plan YAML values when both are specified.

### Pre-Task Check in Orchestrator

In run_orchestrator(), before each task execution:

1. Call budget_guard.can_proceed()
2. If False, mark plan status as "paused_quota" and stop the loop
3. Print a clear message: "Stopping: budget at $X.XX / $Y.YY (ZZ% of ceiling)"
4. After each task completes, call budget_guard.record_cost(task_result.usage.total_cost_usd)

The check happens in the main task loop (sequential execution block around line 1952 and parallel execution block around line 1800).

### Plan Pause Behavior

When budget is exhausted:

1. The current task completes (no mid-task interruption)
2. Plan YAML is updated: meta.status becomes "paused_quota"
3. A pause_reason is written to the plan meta
4. The usage report is generated (from PlanUsageTracker)
5. run_orchestrator() exits with code 0 (not a failure)

A paused plan can be resumed later with --resume-from, and the budget guard re-evaluates from current spending.

### Auto-Pipeline Integration

The auto-pipeline tracks session-level spending across work items:

1. After each work item (process_item), read the usage report to get cost
2. Accumulate session total in a PipelineBudgetTracker
3. Before starting the next work item, check if session budget allows it
4. If not, log the reason and stop the pipeline loop

The auto-pipeline gets budget config from its own CLI flags:

    --max-budget-pct N     Maximum % of quota ceiling for session
    --quota-ceiling N.NN   Weekly quota ceiling in USD

### Exit Codes

The orchestrator uses specific exit behavior for budget pauses:

- Exit code 0: Plan paused due to budget (not a failure)
- The auto-pipeline detects "paused_quota" in the plan YAML after execution
- This is distinct from exit code 1 (real failure) and rate-limit retries

---

## Key Files

### Modified Files

| File | Change |
|------|--------|
| scripts/plan-orchestrator.py | BudgetConfig, BudgetGuard, pre-task check, CLI flags, plan pause logic |
| scripts/auto-pipeline.py | Session budget tracking, per-work-item check, CLI flags |

### New Files

| File | Purpose |
|------|---------|
| tests/test_budget_guard.py | Unit tests for BudgetConfig, BudgetGuard |

---

## Design Decisions

1. **User-configured ceiling, not API-queried quota.** There is no known programmatic API to query remaining Claude weekly quota. The pragmatic approach is a user-configured ceiling combined with locally-tracked cost. This is simple, requires no API access, and works across all plan types.

2. **BudgetGuard is separate from CircuitBreaker.** The circuit breaker handles task failures and rate limits. The budget guard handles cost thresholds. These are orthogonal concerns and should not be merged.

3. **CLI flags override plan YAML.** This lets users run the same plan with different budgets (e.g., more conservative overnight). The plan YAML provides defaults, the CLI provides overrides.

4. **Pause, don't fail.** Budget exhaustion is a normal operational condition, not an error. The plan is paused, not failed, and can be resumed when more budget is available.

5. **No cost estimation or prediction.** The "nice to have" cost estimation from the backlog item is deferred. Predicting task cost requires historical data that does not yet exist. The MVP simply checks "have we spent too much?" before each task.

6. **Session-scoped spending, not weekly aggregation.** Tracking weekly spending across sessions would require reading all historical usage reports and summing them for the current billing week. This adds complexity (billing cycle detection, timezone handling). The MVP tracks spending within a single orchestrator run or pipeline session. Users can set their ceiling to account for prior spending manually.

7. **BudgetConfig lives in plan-orchestrator.py.** Following the single-file convention established by TaskResult, CircuitBreaker, and PlanUsageTracker.
