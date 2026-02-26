# tests/langgraph/executor/nodes/test_task_selector.py
# Unit tests for the find_next_task executor node.
# Design: docs/plans/2026-02-26-05-task-execution-subgraph-design.md

"""Tests for langgraph_pipeline.executor.nodes.task_selector."""

import yaml
import pytest

from langgraph_pipeline.executor.nodes.task_selector import (
    PENDING_STATUS,
    TERMINAL_STATUSES,
    _collect_tasks,
    _completed_task_ids,
    _find_eligible_task,
    _is_budget_exceeded,
    _load_plan_yaml,
    find_next_task,
)

# ─── Fixtures ─────────────────────────────────────────────────────────────────


def _make_state(**overrides) -> dict:
    """Build a minimal TaskState dict for tests."""
    base = {
        "plan_path": "",
        "plan_data": None,
        "current_task_id": None,
        "task_attempt": 0,
        "task_results": [],
        "effective_model": "haiku",
        "consecutive_failures": 0,
        "last_validation_verdict": None,
        "plan_cost_usd": 0.0,
        "plan_input_tokens": 0,
        "plan_output_tokens": 0,
    }
    base.update(overrides)
    return base


def _make_plan(*tasks, budget_limit_usd=None) -> dict:
    """Build a minimal plan dict with a single section containing the given tasks."""
    meta = {"name": "Test Plan", "max_attempts_default": 3}
    if budget_limit_usd is not None:
        meta["budget_limit_usd"] = budget_limit_usd
    return {
        "meta": meta,
        "sections": [{"id": "s1", "name": "Section 1", "tasks": list(tasks)}],
    }


def _make_task(task_id: str, status: str = "pending", deps=None, parallel_group=None) -> dict:
    """Build a minimal task dict."""
    task: dict = {"id": task_id, "name": f"Task {task_id}", "status": status}
    if deps is not None:
        task["dependencies"] = deps
    if parallel_group is not None:
        task["parallel_group"] = parallel_group
    return task


# ─── Tests: _load_plan_yaml ───────────────────────────────────────────────────


class TestLoadPlanYaml:
    """_load_plan_yaml reads and parses a YAML file from disk."""

    def test_parses_valid_yaml(self, tmp_path):
        plan = _make_plan(_make_task("1.1"))
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(yaml.dump(plan))
        result = _load_plan_yaml(str(plan_file))
        assert result["meta"]["name"] == "Test Plan"

    def test_returns_empty_dict_for_blank_file(self, tmp_path):
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text("")
        result = _load_plan_yaml(str(plan_file))
        assert result == {}

    def test_raises_on_missing_file(self, tmp_path):
        with pytest.raises(IOError):
            _load_plan_yaml(str(tmp_path / "missing.yaml"))


# ─── Tests: _collect_tasks ────────────────────────────────────────────────────


class TestCollectTasks:
    """_collect_tasks flattens tasks from all sections into one list."""

    def test_single_section(self):
        plan = _make_plan(_make_task("1.1"), _make_task("1.2"))
        assert len(_collect_tasks(plan)) == 2

    def test_multiple_sections(self):
        plan = {
            "sections": [
                {"tasks": [_make_task("1.1"), _make_task("1.2")]},
                {"tasks": [_make_task("2.1")]},
            ]
        }
        assert len(_collect_tasks(plan)) == 3

    def test_empty_plan(self):
        assert _collect_tasks({}) == []

    def test_section_with_no_tasks_key(self):
        plan = {"sections": [{"id": "s1", "name": "Empty section"}]}
        assert _collect_tasks(plan) == []


# ─── Tests: _completed_task_ids ───────────────────────────────────────────────


class TestCompletedTaskIds:
    """_completed_task_ids returns only tasks with terminal statuses."""

    def test_completed_included(self):
        tasks = [_make_task("1.1", "completed")]
        assert "1.1" in _completed_task_ids(tasks)

    def test_failed_included(self):
        tasks = [_make_task("1.1", "failed")]
        assert "1.1" in _completed_task_ids(tasks)

    def test_skipped_included(self):
        tasks = [_make_task("1.1", "skipped")]
        assert "1.1" in _completed_task_ids(tasks)

    def test_pending_excluded(self):
        tasks = [_make_task("1.1", "pending")]
        assert "1.1" not in _completed_task_ids(tasks)

    def test_in_progress_excluded(self):
        tasks = [_make_task("1.1", "in_progress")]
        assert "1.1" not in _completed_task_ids(tasks)

    def test_mixed_statuses(self):
        tasks = [
            _make_task("1.1", "completed"),
            _make_task("1.2", "pending"),
            _make_task("1.3", "failed"),
        ]
        result = _completed_task_ids(tasks)
        assert result == {"1.1", "1.3"}


# ─── Tests: _is_budget_exceeded ───────────────────────────────────────────────


class TestIsBudgetExceeded:
    """_is_budget_exceeded returns True only when limit is configured and reached."""

    def test_no_limit_never_exceeded(self):
        state = _make_state(plan_cost_usd=999.0)
        assert _is_budget_exceeded(state, _make_plan()) is False

    def test_below_limit(self):
        state = _make_state(plan_cost_usd=0.5)
        plan = _make_plan(budget_limit_usd=1.0)
        assert _is_budget_exceeded(state, plan) is False

    def test_exactly_at_limit(self):
        state = _make_state(plan_cost_usd=1.0)
        plan = _make_plan(budget_limit_usd=1.0)
        assert _is_budget_exceeded(state, plan) is True

    def test_above_limit(self):
        state = _make_state(plan_cost_usd=1.5)
        plan = _make_plan(budget_limit_usd=1.0)
        assert _is_budget_exceeded(state, plan) is True

    def test_zero_cost_zero_limit(self):
        state = _make_state(plan_cost_usd=0.0)
        plan = _make_plan(budget_limit_usd=0.0)
        assert _is_budget_exceeded(state, plan) is True


# ─── Tests: _find_eligible_task ───────────────────────────────────────────────


class TestFindEligibleTask:
    """_find_eligible_task returns first pending task with satisfied dependencies."""

    def test_no_deps_immediately_eligible(self):
        task = _make_task("1.1")
        result = _find_eligible_task([task], set())
        assert result is not None
        assert result["id"] == "1.1"

    def test_satisfied_deps_eligible(self):
        task = _make_task("1.2", deps=["1.1"])
        result = _find_eligible_task([task], {"1.1"})
        assert result is not None
        assert result["id"] == "1.2"

    def test_unsatisfied_dep_not_eligible(self):
        task = _make_task("1.2", deps=["1.1"])
        result = _find_eligible_task([task], set())
        assert result is None

    def test_returns_first_eligible(self):
        tasks = [_make_task("1.2", deps=["1.1"]), _make_task("2.1")]
        result = _find_eligible_task(tasks, set())
        assert result is not None
        assert result["id"] == "2.1"

    def test_all_eligible_returns_first(self):
        tasks = [_make_task("1.1"), _make_task("1.2")]
        result = _find_eligible_task(tasks, set())
        assert result is not None
        assert result["id"] == "1.1"

    def test_empty_pending_returns_none(self):
        assert _find_eligible_task([], set()) is None


# ─── Tests: find_next_task node ───────────────────────────────────────────────


class TestFindNextTaskNode:
    """find_next_task selects the next pending task or stops execution."""

    def test_selects_first_pending_task(self, tmp_path):
        plan = _make_plan(_make_task("1.1"))
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(yaml.dump(plan))
        state = _make_state(plan_path=str(plan_file))

        result = find_next_task(state)

        assert result["current_task_id"] == "1.1"
        assert result["plan_data"] is not None

    def test_uses_cached_plan_data(self, tmp_path):
        plan = _make_plan(_make_task("1.1"))
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(yaml.dump(plan))
        state = _make_state(plan_path=str(plan_file), plan_data=plan)

        # Delete the file to prove it reads from cache, not disk
        plan_file.unlink()
        result = find_next_task(state)

        assert result["current_task_id"] == "1.1"

    def test_skips_completed_task(self, tmp_path):
        plan = _make_plan(
            _make_task("1.1", "completed"),
            _make_task("1.2"),
        )
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(yaml.dump(plan))
        state = _make_state(plan_path=str(plan_file))

        result = find_next_task(state)

        assert result["current_task_id"] == "1.2"

    def test_returns_none_when_all_completed(self, tmp_path):
        plan = _make_plan(_make_task("1.1", "completed"))
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(yaml.dump(plan))
        state = _make_state(plan_path=str(plan_file))

        result = find_next_task(state)

        assert result["current_task_id"] is None

    def test_respects_dependency_order(self, tmp_path):
        plan = _make_plan(
            _make_task("1.1", "pending"),
            _make_task("1.2", "pending", deps=["1.1"]),
        )
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(yaml.dump(plan))
        state = _make_state(plan_path=str(plan_file))

        result = find_next_task(state)

        assert result["current_task_id"] == "1.1"

    def test_skips_blocked_task_selects_independent(self, tmp_path):
        plan = _make_plan(
            _make_task("1.1", "pending", deps=["missing"]),
            _make_task("1.2", "pending"),
        )
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(yaml.dump(plan))
        state = _make_state(plan_path=str(plan_file))

        result = find_next_task(state)

        assert result["current_task_id"] == "1.2"

    def test_circuit_breaker_stops_execution(self, tmp_path):
        plan = _make_plan(_make_task("1.1"))
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(yaml.dump(plan))
        state = _make_state(plan_path=str(plan_file), consecutive_failures=3)

        result = find_next_task(state)

        assert result["current_task_id"] is None

    def test_budget_guard_stops_execution(self, tmp_path):
        plan = _make_plan(_make_task("1.1"), budget_limit_usd=1.0)
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(yaml.dump(plan))
        state = _make_state(plan_path=str(plan_file), plan_cost_usd=2.0)

        result = find_next_task(state)

        assert result["current_task_id"] is None

    def test_deadlock_returns_none(self, tmp_path):
        # Both tasks depend on each other (or depend on something never completed).
        plan = _make_plan(
            _make_task("1.1", "pending", deps=["1.2"]),
            _make_task("1.2", "pending", deps=["1.1"]),
        )
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(yaml.dump(plan))
        state = _make_state(plan_path=str(plan_file))

        result = find_next_task(state)

        assert result["current_task_id"] is None

    def test_selects_task_after_dep_completes(self, tmp_path):
        plan = _make_plan(
            _make_task("1.1", "completed"),
            _make_task("1.2", "pending", deps=["1.1"]),
        )
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(yaml.dump(plan))
        state = _make_state(plan_path=str(plan_file))

        result = find_next_task(state)

        assert result["current_task_id"] == "1.2"

    def test_plan_data_returned_in_result(self, tmp_path):
        plan = _make_plan(_make_task("1.1"))
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(yaml.dump(plan))
        state = _make_state(plan_path=str(plan_file))

        result = find_next_task(state)

        assert "plan_data" in result
        assert result["plan_data"]["meta"]["name"] == "Test Plan"
