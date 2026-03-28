# Quota-Aware Execution with Weekly Budget Limits - Design Document

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

Feature 06 is already implemented.

### BudgetConfig Dataclass

New dataclass to hold budget configuration, placed after PlanUsageTracker in plan-orchestrator.py:

    @dataclass
    class BudgetConfig:
        """Budget limits for plan execution."""
        max_quota_percent: float = DEFAULT_MAX_QUOTA_PERCENT   # 100.0
        quota_ceiling_usd: float = DEFAULT_QUOTA_CEILING_USD   # 0.0 = unlimited
        reserved_budget_usd: float = DEFAULT_RESERVED_BUDGET_USD  # 0.0

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

        @property
        def is_enabled(self) -> bool:
            """Whether budget enforcement is active."""
            return self.quota_ceiling_usd > 0

Configuration sources (in priority order):
1. CLI flags: --max-budget-pct, --quota-ceiling, --reserved-budget
2. Plan YAML meta.budget block
3. Defaults (100% / unlimited = no budget enforcement)

### BudgetGuard Class

Stateful guard that wraps PlanUsageTracker and enforces limits. It does not maintain its own cost counter; it queries the tracker directly.

    class BudgetGuard:
        """Checks cumulative cost against budget limits before each task."""

        def __init__(self, config: BudgetConfig, usage_tracker: PlanUsageTracker):
            self.config = config
            self.usage_tracker = usage_tracker

        def can_proceed(self) -> tuple[bool, str]:
            """Check if budget allows another task.
            Returns (can_proceed, reason_if_not).
            """
            if not self.config.is_enabled:
                return (True, "")
            total = self.usage_tracker.get_total_usage()
            spent = total.total_cost_usd
            limit = self.config.effective_limit_usd
            if spent >= limit:
                pct = (spent / self.config.quota_ceiling_usd * 100) if self.config.quota_ceiling_usd > 0 else 0
                reason = (
                    f"Budget limit reached: ${spent:.4f} / ${limit:.4f} "
                    f"({pct:.1f}% of ${self.config.quota_ceiling_usd:.2f} ceiling)"
                )
                return (False, reason)
            return (True, "")

        def get_usage_percent(self) -> float:
            """Current spending as percentage of ceiling."""
            if not self.config.is_enabled:
                return 0.0
            total = self.usage_tracker.get_total_usage()
            return (total.total_cost_usd / self.config.quota_ceiling_usd * 100)

        def format_status(self) -> str:
            """Format current budget status for display."""
            if not self.config.is_enabled:
                return "[Budget: unlimited]"
            total = self.usage_tracker.get_total_usage()
            spent = total.total_cost_usd
            limit = self.config.effective_limit_usd
            pct = self.get_usage_percent()
            return f"[Budget: ${spent:.4f} / ${limit:.4f} ({pct:.1f}% of ceiling)]"

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

    --max-budget-pct N       Maximum % of quota ceiling to use (default: 100)
    --quota-ceiling N.NN     Weekly quota ceiling in USD (default: 0 = unlimited)
    --reserved-budget N.NN   USD amount to reserve for interactive use (default: 0)

CLI flags override plan YAML values when both are specified.

### parse_budget_config Helper

A helper function parses BudgetConfig from both the plan meta and CLI args:

    def parse_budget_config(plan: dict, args: argparse.Namespace) -> BudgetConfig:
        """Parse budget configuration from plan YAML and CLI overrides."""
        budget_meta = plan.get("meta", {}).get("budget", {})
        config = BudgetConfig(
            max_quota_percent=budget_meta.get("max_quota_percent", DEFAULT_MAX_QUOTA_PERCENT),
            quota_ceiling_usd=budget_meta.get("quota_ceiling_usd", DEFAULT_QUOTA_CEILING_USD),
            reserved_budget_usd=budget_meta.get("reserved_budget_usd", DEFAULT_RESERVED_BUDGET_USD),
        )
        # CLI overrides
        if hasattr(args, 'max_budget_pct') and args.max_budget_pct is not None:
            config.max_quota_percent = args.max_budget_pct
        if hasattr(args, 'quota_ceiling') and args.quota_ceiling is not None:
            config.quota_ceiling_usd = args.quota_ceiling
        if hasattr(args, 'reserved_budget') and args.reserved_budget is not None:
            config.reserved_budget_usd = args.reserved_budget
        return config

### Pre-Task Check in Orchestrator

In run_orchestrator(), after the existing circuit breaker check and before task execution:

1. Call budget_guard.can_proceed()
2. If False, print the reason, set meta.status to "paused_quota", save the plan, and break
3. After each task completes, the usage is already recorded in usage_tracker (no extra step needed since BudgetGuard reads from it)

The check happens in the main task loop:
- Sequential path (around line 2374, after circuit breaker check)
- Parallel path (around line 2396, before parallel group execution)

### Plan Pause Behavior

When budget is exhausted:

1. The current task completes (no mid-task interruption)
2. Plan YAML is updated: meta.status becomes "paused_quota"
3. A meta.pause_reason is written with the budget explanation
4. The usage report is generated (from PlanUsageTracker)
5. run_orchestrator() exits with code 0 (not a failure)

A paused plan can be resumed later with --resume-from, and the budget guard re-evaluates from current spending.

### Auto-Pipeline Integration

The auto-pipeline checks session-level spending across work items using SessionUsageTracker.total_cost_usd:

1. Parse budget config from CLI flags (--max-budget-pct, --quota-ceiling)
2. Create a PipelineBudgetGuard that checks SessionUsageTracker.total_cost_usd against the ceiling
3. Before starting each new work item, check can_proceed()
4. If budget exhausted, log the reason and break the main loop

The auto-pipeline budget check is per-work-item (coarser granularity than per-task).

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
| scripts/plan-orchestrator.py | BudgetConfig, BudgetGuard, parse_budget_config, pre-task check, CLI flags, plan pause logic |
| scripts/auto-pipeline.py | PipelineBudgetGuard, per-work-item check, CLI flags |

### New Files

| File | Purpose |
|------|---------|
| tests/test_budget_guard.py | Unit tests for BudgetConfig, BudgetGuard, parse_budget_config |

---

## Design Decisions

1. **User-configured ceiling, not API-queried quota.** There is no known programmatic API to query remaining Claude weekly quota. The pragmatic approach is a user-configured ceiling combined with locally-tracked cost. This is simple, requires no API access, and works across all plan types.

2. **BudgetGuard wraps PlanUsageTracker, not a separate cost counter.** Instead of maintaining its own running cost total, BudgetGuard queries PlanUsageTracker.get_total_usage().total_cost_usd directly. This avoids duplicate state and keeps cost data in one authoritative place.

3. **BudgetGuard is separate from CircuitBreaker.** The circuit breaker handles task failures and rate limits. The budget guard handles cost thresholds. These are orthogonal concerns and should not be merged.

4. **CLI flags override plan YAML.** This lets users run the same plan with different budgets (e.g., more conservative overnight). The plan YAML provides defaults, the CLI provides overrides.

5. **Pause, don't fail.** Budget exhaustion is a normal operational condition, not an error. The plan is paused, not failed, and can be resumed when more budget is available. Exit code 0 signals this.

6. **Session-scoped spending, not weekly aggregation.** Tracking weekly spending across sessions would require reading all historical usage reports and summing them for the current billing week. This adds complexity (billing cycle detection, timezone handling). The MVP tracks spending within a single orchestrator run or pipeline session. Users can set their ceiling to account for prior spending manually.

7. **BudgetConfig and BudgetGuard live in plan-orchestrator.py.** Following the single-file convention established by TaskResult, CircuitBreaker, and PlanUsageTracker.

8. **No cost estimation or prediction.** The "nice to have" cost estimation from the backlog item is deferred. Predicting task cost requires historical data that does not yet exist. The MVP checks "have we spent too much?" before each task.
