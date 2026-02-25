# tests/langgraph/shared/test_budget.py
# Unit tests for the shared budget module.
# Design: docs/plans/2026-02-25-02-extract-shared-modules-design.md

"""Unit tests for langgraph_pipeline.shared.budget."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

from langgraph_pipeline.shared.budget import (
    DEFAULT_MAX_QUOTA_PERCENT,
    DEFAULT_QUOTA_CEILING_USD,
    DEFAULT_RESERVED_BUDGET_USD,
    MAX_PLAN_NAME_LENGTH,
    SCOPE_PLAN,
    SCOPE_SESSION,
    BudgetConfig,
    BudgetGuard,
    TaskUsage,
    UsageTracker,
)


# ─── Constants ────────────────────────────────────────────────────────────────


class TestConstants:
    def test_default_max_quota_percent_is_100(self):
        assert DEFAULT_MAX_QUOTA_PERCENT == 100.0

    def test_default_quota_ceiling_is_zero(self):
        assert DEFAULT_QUOTA_CEILING_USD == 0.0

    def test_default_reserved_budget_is_zero(self):
        assert DEFAULT_RESERVED_BUDGET_USD == 0.0

    def test_max_plan_name_length_is_positive(self):
        assert MAX_PLAN_NAME_LENGTH > 0

    def test_scope_plan_is_string(self):
        assert isinstance(SCOPE_PLAN, str)

    def test_scope_session_is_string(self):
        assert isinstance(SCOPE_SESSION, str)

    def test_scopes_are_distinct(self):
        assert SCOPE_PLAN != SCOPE_SESSION


# ─── TaskUsage ────────────────────────────────────────────────────────────────


class TestTaskUsage:
    def test_default_values_are_zero(self):
        u = TaskUsage()
        assert u.input_tokens == 0
        assert u.output_tokens == 0
        assert u.cache_read_tokens == 0
        assert u.cache_creation_tokens == 0
        assert u.total_cost_usd == 0.0
        assert u.num_turns == 0
        assert u.duration_api_ms == 0

    def test_fields_can_be_set(self):
        u = TaskUsage(input_tokens=100, output_tokens=50, total_cost_usd=0.01)
        assert u.input_tokens == 100
        assert u.output_tokens == 50
        assert u.total_cost_usd == 0.01


# ─── BudgetConfig ─────────────────────────────────────────────────────────────


class TestBudgetConfig:
    def test_defaults_match_constants(self):
        cfg = BudgetConfig()
        assert cfg.max_quota_percent == DEFAULT_MAX_QUOTA_PERCENT
        assert cfg.quota_ceiling_usd == DEFAULT_QUOTA_CEILING_USD
        assert cfg.reserved_budget_usd == DEFAULT_RESERVED_BUDGET_USD

    def test_is_enabled_false_when_ceiling_is_zero(self):
        cfg = BudgetConfig(quota_ceiling_usd=0.0)
        assert cfg.is_enabled is False

    def test_is_enabled_true_when_ceiling_set(self):
        cfg = BudgetConfig(quota_ceiling_usd=10.0)
        assert cfg.is_enabled is True

    def test_effective_limit_inf_when_disabled(self):
        cfg = BudgetConfig(quota_ceiling_usd=0.0)
        assert cfg.effective_limit_usd == float("inf")

    def test_effective_limit_applies_percent(self):
        cfg = BudgetConfig(quota_ceiling_usd=100.0, max_quota_percent=80.0)
        assert cfg.effective_limit_usd == 80.0

    def test_effective_limit_applies_reserve(self):
        cfg = BudgetConfig(quota_ceiling_usd=100.0, reserved_budget_usd=20.0, max_quota_percent=100.0)
        assert cfg.effective_limit_usd == 80.0

    def test_effective_limit_uses_min_of_percent_and_reserve(self):
        # percent_limit = 100 * 0.5 = 50, reserve_limit = 100 - 10 = 90 → min is 50
        cfg = BudgetConfig(quota_ceiling_usd=100.0, max_quota_percent=50.0, reserved_budget_usd=10.0)
        assert cfg.effective_limit_usd == 50.0

    def test_effective_limit_ignores_zero_reserve(self):
        cfg = BudgetConfig(quota_ceiling_usd=100.0, max_quota_percent=75.0, reserved_budget_usd=0.0)
        assert cfg.effective_limit_usd == 75.0


# ─── UsageTracker (construction) ──────────────────────────────────────────────


class TestUsageTrackerConstruction:
    def test_default_scope_is_plan(self):
        t = UsageTracker()
        assert t.scope == SCOPE_PLAN

    def test_plan_scope_accepted(self):
        t = UsageTracker(scope=SCOPE_PLAN)
        assert t.scope == SCOPE_PLAN

    def test_session_scope_accepted(self):
        t = UsageTracker(scope=SCOPE_SESSION)
        assert t.scope == SCOPE_SESSION

    def test_invalid_scope_raises(self):
        with pytest.raises(ValueError, match="Invalid scope"):
            UsageTracker(scope="invalid")

    def test_initial_state_is_empty(self):
        t = UsageTracker()
        assert t.task_usages == {}
        assert t.total_cost_usd == 0.0
        assert t.work_item_costs == []


# ─── UsageTracker - plan scope ────────────────────────────────────────────────


class TestUsageTrackerPlanScope:
    def _tracker_with_tasks(self) -> UsageTracker:
        t = UsageTracker(scope=SCOPE_PLAN)
        t.record("1.1", TaskUsage(input_tokens=100, output_tokens=50, total_cost_usd=0.05))
        t.record("1.2", TaskUsage(input_tokens=200, output_tokens=80, total_cost_usd=0.10), model="claude-3")
        return t

    def test_record_stores_usage(self):
        t = UsageTracker(scope=SCOPE_PLAN)
        u = TaskUsage(input_tokens=100, total_cost_usd=0.01)
        t.record("1.1", u)
        assert "1.1" in t.task_usages

    def test_record_stores_model(self):
        t = UsageTracker(scope=SCOPE_PLAN)
        t.record("1.1", TaskUsage(), model="claude-3")
        assert t.task_models["1.1"] == "claude-3"

    def test_get_total_usage_sums_all_tasks(self):
        t = self._tracker_with_tasks()
        total = t.get_total_usage()
        assert total.input_tokens == 300
        assert total.output_tokens == 130
        assert abs(total.total_cost_usd - 0.15) < 1e-9

    def test_get_total_usage_empty_returns_zeros(self):
        t = UsageTracker(scope=SCOPE_PLAN)
        total = t.get_total_usage()
        assert total.total_cost_usd == 0.0

    def test_get_cache_hit_rate_with_no_data_returns_zero(self):
        t = UsageTracker(scope=SCOPE_PLAN)
        assert t.get_cache_hit_rate() == 0.0

    def test_get_cache_hit_rate_calculates_correctly(self):
        t = UsageTracker(scope=SCOPE_PLAN)
        t.record("1.1", TaskUsage(input_tokens=100, cache_read_tokens=400))
        # hit rate = 400 / (400 + 100) = 0.8
        assert abs(t.get_cache_hit_rate() - 0.8) < 1e-9

    def test_get_section_usage_aggregates_section_tasks(self):
        t = UsageTracker(scope=SCOPE_PLAN)
        t.record("1.1", TaskUsage(total_cost_usd=0.05))
        t.record("1.2", TaskUsage(total_cost_usd=0.03))
        t.record("2.1", TaskUsage(total_cost_usd=0.10))
        plan = {
            "sections": [
                {"id": "phase-1", "tasks": [{"id": "1.1"}, {"id": "1.2"}]},
                {"id": "phase-2", "tasks": [{"id": "2.1"}]},
            ]
        }
        su = t.get_section_usage(plan, "phase-1")
        assert abs(su.total_cost_usd - 0.08) < 1e-9

    def test_get_section_usage_returns_zero_for_unknown_section(self):
        t = UsageTracker(scope=SCOPE_PLAN)
        plan = {"sections": [{"id": "phase-1", "tasks": []}]}
        su = t.get_section_usage(plan, "nonexistent")
        assert su.total_cost_usd == 0.0

    def test_format_summary_line_returns_empty_for_unknown_task(self):
        t = UsageTracker(scope=SCOPE_PLAN)
        assert t.format_summary_line("9.9") == ""

    def test_format_summary_line_includes_task_id(self):
        t = self._tracker_with_tasks()
        line = t.format_summary_line("1.1")
        assert "1.1" in line

    def test_format_summary_line_includes_model(self):
        t = self._tracker_with_tasks()
        line = t.format_summary_line("1.2")
        assert "claude-3" in line

    def test_format_summary_line_includes_cost(self):
        t = self._tracker_with_tasks()
        line = t.format_summary_line("1.1")
        assert "$0.0500" in line

    def test_format_final_summary_includes_totals(self):
        t = self._tracker_with_tasks()
        summary = t.format_final_summary({})
        assert "Usage Summary" in summary
        assert "API-Equivalent" in summary

    def test_format_final_summary_includes_section_breakdown(self):
        t = UsageTracker(scope=SCOPE_PLAN)
        t.record("1.1", TaskUsage(total_cost_usd=0.05))
        plan = {
            "sections": [
                {"id": "s1", "name": "Phase One", "tasks": [{"id": "1.1"}]}
            ]
        }
        summary = t.format_final_summary(plan)
        assert "Phase One" in summary

    def test_write_report_returns_none_when_no_data(self):
        t = UsageTracker(scope=SCOPE_PLAN)
        result = t.write_report({}, "plan.yaml")
        assert result is None

    def test_write_report_writes_json_file(self):
        t = UsageTracker(scope=SCOPE_PLAN)
        t.record("1.1", TaskUsage(total_cost_usd=0.05, input_tokens=100))
        plan = {"meta": {"name": "test-plan"}, "sections": []}

        with patch("langgraph_pipeline.shared.budget.open", mock_open()) as m:
            with patch("langgraph_pipeline.shared.budget.json.dump") as mock_dump:
                result = t.write_report(plan, "plan.yaml")
        assert result is not None
        assert "test-plan" in str(result)

    def test_write_report_truncates_long_plan_names(self):
        t = UsageTracker(scope=SCOPE_PLAN)
        t.record("1.1", TaskUsage(total_cost_usd=0.01))
        long_name = "a" * 200
        plan = {"meta": {"name": long_name}, "sections": []}

        with patch("langgraph_pipeline.shared.budget.open", mock_open()):
            with patch("langgraph_pipeline.shared.budget.json.dump"):
                result = t.write_report(plan, "plan.yaml")

        stem = result.stem  # filename without extension
        plan_part = stem.replace("-usage-report", "")
        assert len(plan_part) <= MAX_PLAN_NAME_LENGTH


# ─── UsageTracker - session scope ─────────────────────────────────────────────


class TestUsageTrackerSessionScope:
    def test_record_from_report_accumulates_cost(self):
        t = UsageTracker(scope=SCOPE_SESSION)
        report_data = json.dumps({"total": {"cost_usd": 0.25, "input_tokens": 500, "output_tokens": 200}})
        with patch("builtins.open", mock_open(read_data=report_data)):
            t.record_from_report("report.json", "my-feature")
        assert abs(t.total_cost_usd - 0.25) < 1e-9

    def test_record_from_report_accumulates_tokens(self):
        t = UsageTracker(scope=SCOPE_SESSION)
        report_data = json.dumps({"total": {"cost_usd": 0.10, "input_tokens": 300, "output_tokens": 150}})
        with patch("builtins.open", mock_open(read_data=report_data)):
            t.record_from_report("report.json", "item")
        assert t.total_input_tokens == 300
        assert t.total_output_tokens == 150

    def test_record_from_report_appends_work_item(self):
        t = UsageTracker(scope=SCOPE_SESSION)
        report_data = json.dumps({"total": {"cost_usd": 0.05}})
        with patch("builtins.open", mock_open(read_data=report_data)):
            t.record_from_report("report.json", "my-work-item")
        assert len(t.work_item_costs) == 1
        assert t.work_item_costs[0]["name"] == "my-work-item"

    def test_record_from_report_silences_file_not_found(self):
        t = UsageTracker(scope=SCOPE_SESSION)
        with patch("builtins.open", side_effect=FileNotFoundError):
            t.record_from_report("missing.json", "item")
        assert t.total_cost_usd == 0.0

    def test_record_from_report_silences_bad_json(self):
        t = UsageTracker(scope=SCOPE_SESSION)
        with patch("builtins.open", mock_open(read_data="not-json")):
            t.record_from_report("bad.json", "item")
        assert t.total_cost_usd == 0.0

    def test_format_session_summary_includes_total_cost(self):
        t = UsageTracker(scope=SCOPE_SESSION)
        t.total_cost_usd = 1.2345
        summary = t.format_session_summary()
        assert "1.2345" in summary

    def test_format_session_summary_includes_per_item_breakdown(self):
        t = UsageTracker(scope=SCOPE_SESSION)
        t.work_item_costs = [{"name": "feature-x", "cost_usd": 0.50}]
        t.total_cost_usd = 0.50
        summary = t.format_session_summary()
        assert "feature-x" in summary

    def test_write_session_report_returns_none_when_empty(self):
        t = UsageTracker(scope=SCOPE_SESSION)
        result = t.write_session_report()
        assert result is None

    def test_write_session_report_writes_json_file(self):
        t = UsageTracker(scope=SCOPE_SESSION)
        t.work_item_costs = [{"name": "item", "cost_usd": 0.10}]
        t.total_cost_usd = 0.10

        with patch("langgraph_pipeline.shared.budget.open", mock_open()) as m:
            with patch("langgraph_pipeline.shared.budget.json.dump") as mock_dump:
                result = t.write_session_report()
        assert result is not None
        assert "pipeline-session-" in result


# ─── BudgetGuard ──────────────────────────────────────────────────────────────


class TestBudgetGuard:
    def _guard(self, ceiling: float, percent: float = 100.0, reserved: float = 0.0,
               scope: str = SCOPE_PLAN) -> tuple["BudgetGuard", "UsageTracker"]:
        config = BudgetConfig(
            max_quota_percent=percent,
            quota_ceiling_usd=ceiling,
            reserved_budget_usd=reserved,
        )
        tracker = UsageTracker(scope=scope)
        guard = BudgetGuard(config, tracker)
        return guard, tracker

    # ─── can_proceed - disabled budget ────────────────────────────────────────

    def test_can_proceed_true_when_budget_disabled(self):
        guard, _ = self._guard(ceiling=0.0)
        ok, reason = guard.can_proceed()
        assert ok is True
        assert reason == ""

    # ─── can_proceed - plan scope (no explicit cost) ──────────────────────────

    def test_can_proceed_true_when_under_limit(self):
        guard, tracker = self._guard(ceiling=10.0)
        tracker.record("1.1", TaskUsage(total_cost_usd=5.0))
        ok, reason = guard.can_proceed()
        assert ok is True

    def test_can_proceed_false_when_at_limit(self):
        guard, tracker = self._guard(ceiling=10.0)
        tracker.record("1.1", TaskUsage(total_cost_usd=10.0))
        ok, reason = guard.can_proceed()
        assert ok is False

    def test_can_proceed_reason_includes_spend_and_limit(self):
        guard, tracker = self._guard(ceiling=10.0)
        tracker.record("1.1", TaskUsage(total_cost_usd=10.0))
        _, reason = guard.can_proceed()
        assert "$10.0000" in reason
        assert "$10.0000" in reason

    def test_can_proceed_false_when_exceeds_percent_limit(self):
        guard, tracker = self._guard(ceiling=10.0, percent=50.0)
        tracker.record("1.1", TaskUsage(total_cost_usd=5.1))
        ok, _ = guard.can_proceed()
        assert ok is False

    # ─── can_proceed - explicit cost (pipeline pattern) ───────────────────────

    def test_can_proceed_uses_explicit_cost_when_provided(self):
        guard, tracker = self._guard(ceiling=10.0)
        # Tracker is empty, but we pass explicit cost at limit
        ok, reason = guard.can_proceed(cost_usd=10.0)
        assert ok is False

    def test_can_proceed_explicit_cost_under_limit(self):
        guard, tracker = self._guard(ceiling=10.0)
        ok, _ = guard.can_proceed(cost_usd=3.0)
        assert ok is True

    # ─── can_proceed - session scope ──────────────────────────────────────────

    def test_can_proceed_reads_session_tracker_total(self):
        guard, tracker = self._guard(ceiling=5.0, scope=SCOPE_SESSION)
        tracker.total_cost_usd = 5.0
        ok, _ = guard.can_proceed()
        assert ok is False

    def test_can_proceed_session_under_limit(self):
        guard, tracker = self._guard(ceiling=5.0, scope=SCOPE_SESSION)
        tracker.total_cost_usd = 2.0
        ok, _ = guard.can_proceed()
        assert ok is True

    # ─── get_usage_percent ────────────────────────────────────────────────────

    def test_get_usage_percent_returns_zero_when_disabled(self):
        guard, _ = self._guard(ceiling=0.0)
        assert guard.get_usage_percent() == 0.0

    def test_get_usage_percent_calculates_correctly(self):
        guard, tracker = self._guard(ceiling=100.0)
        tracker.record("1.1", TaskUsage(total_cost_usd=40.0))
        assert abs(guard.get_usage_percent() - 40.0) < 1e-9

    def test_get_usage_percent_session_scope(self):
        guard, tracker = self._guard(ceiling=100.0, scope=SCOPE_SESSION)
        tracker.total_cost_usd = 75.0
        assert abs(guard.get_usage_percent() - 75.0) < 1e-9

    # ─── format_status ────────────────────────────────────────────────────────

    def test_format_status_unlimited_when_disabled(self):
        guard, _ = self._guard(ceiling=0.0)
        status = guard.format_status()
        assert "unlimited" in status

    def test_format_status_includes_spent_and_limit(self):
        guard, tracker = self._guard(ceiling=10.0)
        tracker.record("1.1", TaskUsage(total_cost_usd=3.0))
        status = guard.format_status()
        assert "$3.0000" in status
        assert "$10.0000" in status

    def test_format_status_includes_percent(self):
        guard, tracker = self._guard(ceiling=100.0)
        tracker.record("1.1", TaskUsage(total_cost_usd=25.0))
        status = guard.format_status()
        assert "25.0%" in status
