# tests/test_budget_guard.py
# Unit tests for BudgetConfig dataclass.
# Design ref: docs/plans/2026-02-14-07-quota-aware-execution-design.md

import importlib.util
import math

# plan-orchestrator.py has a hyphen in the filename, so we must use importlib
# to load it as a module under a valid Python identifier.
spec = importlib.util.spec_from_file_location(
    "plan_orchestrator", "scripts/plan-orchestrator.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

BudgetConfig = mod.BudgetConfig
BudgetGuard = mod.BudgetGuard
PlanUsageTracker = mod.PlanUsageTracker
TaskUsage = mod.TaskUsage


# --- BudgetConfig dataclass tests ---


def test_budget_config_defaults():
    """Default BudgetConfig should be disabled with infinite effective limit."""
    cfg = BudgetConfig()
    assert cfg.max_quota_percent == 100.0
    assert cfg.quota_ceiling_usd == 0.0
    assert cfg.reserved_budget_usd == 0.0
    assert cfg.is_enabled is False
    assert math.isinf(cfg.effective_limit_usd)


def test_budget_config_with_ceiling():
    """Ceiling with percent cap should produce an enabled config."""
    cfg = BudgetConfig(quota_ceiling_usd=100.0, max_quota_percent=90.0)
    assert cfg.is_enabled is True
    assert cfg.effective_limit_usd == 90.0


def test_budget_config_with_reserved():
    """Reserved budget subtracts from ceiling for effective limit."""
    cfg = BudgetConfig(quota_ceiling_usd=100.0, reserved_budget_usd=15.0)
    assert cfg.effective_limit_usd == 85.0


def test_budget_config_percent_and_reserved_takes_minimum():
    """When both percent and reserved are set, effective limit is the minimum."""
    cfg = BudgetConfig(
        quota_ceiling_usd=100.0,
        max_quota_percent=90.0,
        reserved_budget_usd=5.0,
    )
    # percent_limit = 100 * 90/100 = 90.0
    # reserve_limit = 100 - 5 = 95.0
    # min(90.0, 95.0) = 90.0
    assert cfg.effective_limit_usd == 90.0


def test_budget_config_reserved_more_restrictive():
    """When reserved budget is more restrictive than percent, it wins."""
    cfg = BudgetConfig(
        quota_ceiling_usd=100.0,
        max_quota_percent=95.0,
        reserved_budget_usd=20.0,
    )
    # percent_limit = 100 * 95/100 = 95.0
    # reserve_limit = 100 - 20 = 80.0
    # min(95.0, 80.0) = 80.0
    assert cfg.effective_limit_usd == 80.0


def test_budget_config_zero_ceiling_not_enabled():
    """Zero ceiling means budget enforcement is disabled."""
    cfg = BudgetConfig(quota_ceiling_usd=0.0)
    assert cfg.is_enabled is False


# --- BudgetGuard tests ---


def _make_guard(
    quota_ceiling_usd: float = 0.0,
    max_quota_percent: float = 100.0,
    reserved_budget_usd: float = 0.0,
    task_costs: list[float] | None = None,
) -> BudgetGuard:
    """Helper: build a BudgetGuard with optional pre-recorded task costs."""
    config = BudgetConfig(
        quota_ceiling_usd=quota_ceiling_usd,
        max_quota_percent=max_quota_percent,
        reserved_budget_usd=reserved_budget_usd,
    )
    tracker = PlanUsageTracker()
    if task_costs:
        for idx, cost in enumerate(task_costs):
            tracker.record(str(idx), TaskUsage(total_cost_usd=cost))
    return BudgetGuard(config, tracker)


def test_guard_unlimited_always_proceeds():
    """Unlimited budget (no ceiling) always allows proceeding."""
    guard = _make_guard(task_costs=[5.0, 10.0])
    ok, reason = guard.can_proceed()
    assert ok is True
    assert reason == ""


def test_guard_under_budget_proceeds():
    """Spending below the limit allows proceeding."""
    guard = _make_guard(
        quota_ceiling_usd=10.0, max_quota_percent=90.0, task_costs=[5.0]
    )
    ok, reason = guard.can_proceed()
    assert ok is True
    assert reason == ""


def test_guard_at_limit_stops():
    """Spending exactly at the limit triggers a stop."""
    guard = _make_guard(
        quota_ceiling_usd=10.0, max_quota_percent=90.0, task_costs=[4.5, 4.5]
    )
    ok, reason = guard.can_proceed()
    assert ok is False
    assert "Budget limit reached" in reason


def test_guard_over_limit_stops():
    """Spending above the limit triggers a stop."""
    guard = _make_guard(
        quota_ceiling_usd=10.0, max_quota_percent=90.0, task_costs=[5.0, 4.5]
    )
    ok, reason = guard.can_proceed()
    assert ok is False
    assert "Budget limit reached" in reason


def test_guard_usage_percent():
    """Usage percent reflects proportion of total ceiling spent."""
    guard = _make_guard(quota_ceiling_usd=100.0, task_costs=[25.0])
    assert guard.get_usage_percent() == 25.0


def test_guard_format_status_unlimited():
    """Unlimited guard displays '[Budget: unlimited]'."""
    guard = _make_guard()
    assert guard.format_status() == "[Budget: unlimited]"


def test_guard_format_status_with_ceiling():
    """Status string includes both spent and ceiling amounts."""
    guard = _make_guard(quota_ceiling_usd=100.0, task_costs=[30.0])
    status = guard.format_status()
    assert "$30" in status
    assert "$100" in status
