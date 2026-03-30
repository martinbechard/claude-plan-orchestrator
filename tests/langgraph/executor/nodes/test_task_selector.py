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
    _find_validation_pending_task,
    _is_budget_exceeded,
    _load_plan_yaml,
    find_next_task,
)
from langgraph_pipeline.executor.state import effective_status

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


def _make_plan(*tasks, budget_limit_usd=None, validation=None) -> dict:
    """Build a minimal plan dict with a single section containing the given tasks."""
    meta = {"name": "Test Plan", "max_attempts_default": 3}
    if budget_limit_usd is not None:
        meta["budget_limit_usd"] = budget_limit_usd
    if validation is not None:
        meta["validation"] = validation
    return {
        "meta": meta,
        "sections": [{"id": "s1", "name": "Section 1", "tasks": list(tasks)}],
    }


def _make_task(
    task_id: str, status: str = "pending", deps=None, parallel_group=None,
    agent: str = "coder", **extra,
) -> dict:
    """Build a minimal task dict."""
    task: dict = {"id": task_id, "name": f"Task {task_id}", "status": status, "agent": agent}
    if deps is not None:
        task["dependencies"] = deps
    if parallel_group is not None:
        task["parallel_group"] = parallel_group
    task.update(extra)
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
    """_completed_task_ids returns only tasks with terminal effective statuses."""

    # No validation configured: completed tasks are promoted to verified
    _NO_VALIDATION = {}

    # Validation enabled for coder agent
    _VALIDATION_ENABLED = {"enabled": True, "run_after": ["coder"]}

    def test_verified_included(self):
        tasks = [_make_task("1.1", "verified")]
        assert "1.1" in _completed_task_ids(tasks, self._NO_VALIDATION)

    def test_failed_included(self):
        tasks = [_make_task("1.1", "failed")]
        assert "1.1" in _completed_task_ids(tasks, self._NO_VALIDATION)

    def test_skipped_included(self):
        tasks = [_make_task("1.1", "skipped")]
        assert "1.1" in _completed_task_ids(tasks, self._NO_VALIDATION)

    def test_pending_excluded(self):
        tasks = [_make_task("1.1", "pending")]
        assert "1.1" not in _completed_task_ids(tasks, self._NO_VALIDATION)

    def test_in_progress_excluded(self):
        tasks = [_make_task("1.1", "in_progress")]
        assert "1.1" not in _completed_task_ids(tasks, self._NO_VALIDATION)

    def test_completed_promoted_when_no_validation(self):
        """Legacy completed tasks satisfy dependencies when validation is off."""
        tasks = [_make_task("1.1", "completed")]
        assert "1.1" in _completed_task_ids(tasks, self._NO_VALIDATION)

    def test_completed_blocked_when_validation_enabled(self):
        """Tasks awaiting validation do NOT satisfy dependencies (AC11)."""
        task = _make_task("1.1", "completed")
        task["agent"] = "coder"
        assert "1.1" not in _completed_task_ids([task], self._VALIDATION_ENABLED)

    def test_completed_promoted_when_agent_not_in_run_after(self):
        """Completed task whose agent is not validated is promoted to verified."""
        task = _make_task("1.1", "completed")
        task["agent"] = "design-judge"
        validation = {"enabled": True, "run_after": ["coder"]}
        assert "1.1" in _completed_task_ids([task], validation)

    def test_completed_promoted_when_already_validated(self):
        """Completed task that already went through validation is promoted."""
        task = _make_task("1.1", "completed")
        task["agent"] = "coder"
        task["validation_attempts"] = 1
        assert "1.1" in _completed_task_ids([task], self._VALIDATION_ENABLED)

    def test_mixed_statuses_with_validation(self):
        verified_task = _make_task("1.1", "verified")
        completed_task = _make_task("1.2", "completed")
        completed_task["agent"] = "coder"
        pending_task = _make_task("1.3", "pending")
        failed_task = _make_task("1.4", "failed")
        tasks = [verified_task, completed_task, pending_task, failed_task]
        result = _completed_task_ids(tasks, self._VALIDATION_ENABLED)
        # 1.2 is blocked (completed + awaiting validation)
        assert result == {"1.1", "1.4"}


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

    def test_quota_exhausted_stops_task_selection(self):
        # Supplying plan_data directly avoids disk I/O — quota guard fires before task scan
        plan = _make_plan(_make_task("1.1"))
        state = _make_state(quota_exhausted=True, plan_data=plan)

        result = find_next_task(state)

        assert result["current_task_id"] is None

    def test_plan_data_returned_in_result(self, tmp_path):
        plan = _make_plan(_make_task("1.1"))
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(yaml.dump(plan))
        state = _make_state(plan_path=str(plan_file))

        result = find_next_task(state)

        assert "plan_data" in result
        assert result["plan_data"]["meta"]["name"] == "Test Plan"

    def test_completed_blocks_dependent_when_validation_enabled(self, tmp_path):
        """AC11: completed (awaiting validation) blocks dependents; validation is scheduled instead."""
        validation = {"enabled": True, "run_after": ["coder"]}
        plan = _make_plan(
            _make_task("1.1", "completed", agent="coder"),
            _make_task("1.2", "pending", deps=["1.1"]),
            validation=validation,
        )
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(yaml.dump(plan))
        state = _make_state(plan_path=str(plan_file))

        result = find_next_task(state)

        # 1.2 is blocked; find_next_task schedules 1.1 for validation instead
        assert result["current_task_id"] == "1.1"

    def test_verified_satisfies_dependency(self, tmp_path):
        """AC12: verified status satisfies dependency checks."""
        validation = {"enabled": True, "run_after": ["coder"]}
        plan = _make_plan(
            _make_task("1.1", "verified", agent="coder"),
            _make_task("1.2", "pending", deps=["1.1"]),
            validation=validation,
        )
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(yaml.dump(plan))
        state = _make_state(plan_path=str(plan_file))

        result = find_next_task(state)

        assert result["current_task_id"] == "1.2"

    def test_completed_promoted_for_non_validated_agent(self, tmp_path):
        """AC18: completed tasks whose agent is not in run_after are promoted."""
        validation = {"enabled": True, "run_after": ["coder"]}
        plan = _make_plan(
            _make_task("1.1", "completed", agent="design-judge"),
            _make_task("1.2", "pending", deps=["1.1"]),
            validation=validation,
        )
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(yaml.dump(plan))
        state = _make_state(plan_path=str(plan_file))

        result = find_next_task(state)

        assert result["current_task_id"] == "1.2"

    def test_completed_promoted_when_already_validated(self, tmp_path):
        """Completed tasks that already went through validation satisfy deps."""
        validation = {"enabled": True, "run_after": ["coder"]}
        plan = _make_plan(
            _make_task("1.1", "completed", agent="coder", validation_attempts=1),
            _make_task("1.2", "pending", deps=["1.1"]),
            validation=validation,
        )
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(yaml.dump(plan))
        state = _make_state(plan_path=str(plan_file))

        result = find_next_task(state)

        assert result["current_task_id"] == "1.2"

    def test_deadlock_returns_deadlock_detected_true(self, tmp_path):
        """Deadlock branch sets deadlock_detected=True in the returned state."""
        plan = _make_plan(
            _make_task("1.1", "pending", deps=["1.2"]),
            _make_task("1.2", "pending", deps=["1.1"]),
        )
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(yaml.dump(plan))
        state = _make_state(plan_path=str(plan_file))

        result = find_next_task(state)

        assert result["deadlock_detected"] is True

    def test_deadlock_returns_deadlock_details_with_all_blocked_tasks(self, tmp_path):
        """deadlock_details contains an entry for each pending blocked task."""
        plan = _make_plan(
            _make_task("1.1", "pending", deps=["1.2"]),
            _make_task("1.2", "pending", deps=["1.1"]),
        )
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(yaml.dump(plan))
        state = _make_state(plan_path=str(plan_file))

        result = find_next_task(state)

        details = result["deadlock_details"]
        assert details is not None
        assert len(details) == 2
        task_ids = {d["task_id"] for d in details}
        assert task_ids == {"1.1", "1.2"}

    def test_deadlock_details_include_task_name(self, tmp_path):
        """Each deadlock detail entry includes the task name."""
        plan = _make_plan(
            _make_task("1.1", "pending", deps=["1.2"]),
            _make_task("1.2", "pending", deps=["1.1"]),
        )
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(yaml.dump(plan))
        state = _make_state(plan_path=str(plan_file))

        result = find_next_task(state)

        for detail in result["deadlock_details"]:
            assert "task_name" in detail
            assert detail["task_name"]  # non-empty

    def test_deadlock_details_include_unsatisfied_deps(self, tmp_path):
        """Each deadlock detail entry lists the unsatisfied dependency IDs."""
        plan = _make_plan(
            _make_task("1.1", "pending", deps=["1.2"]),
            _make_task("1.2", "pending", deps=["1.1"]),
        )
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(yaml.dump(plan))
        state = _make_state(plan_path=str(plan_file))

        result = find_next_task(state)

        detail_1_1 = next(d for d in result["deadlock_details"] if d["task_id"] == "1.1")
        assert "1.2" in detail_1_1["unsatisfied_deps"]
        detail_1_2 = next(d for d in result["deadlock_details"] if d["task_id"] == "1.2")
        assert "1.1" in detail_1_2["unsatisfied_deps"]

    def test_normal_completion_returns_deadlock_detected_false(self, tmp_path):
        """When all tasks are done, deadlock_detected is False."""
        plan = _make_plan(_make_task("1.1", "completed"))
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(yaml.dump(plan))
        state = _make_state(plan_path=str(plan_file))

        result = find_next_task(state)

        assert result["deadlock_detected"] is False

    def test_task_selected_returns_deadlock_detected_false(self, tmp_path):
        """When a task is selected, deadlock_detected is False."""
        plan = _make_plan(_make_task("1.1"))
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(yaml.dump(plan))
        state = _make_state(plan_path=str(plan_file))

        result = find_next_task(state)

        assert result["deadlock_detected"] is False

    def test_deadlock_emits_warning_log_with_task_ids(self, tmp_path, caplog):
        """Warning log includes blocked task IDs when deadlock is detected."""
        import logging

        plan = _make_plan(
            _make_task("1.1", "pending", deps=["1.2"]),
            _make_task("1.2", "pending", deps=["1.1"]),
        )
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(yaml.dump(plan))
        state = _make_state(plan_path=str(plan_file))

        with caplog.at_level(logging.WARNING, logger="langgraph_pipeline.executor.nodes.task_selector"):
            find_next_task(state)

        warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert warning_records, "Expected at least one WARNING-level log record"
        combined = " ".join(r.getMessage() for r in warning_records)
        assert "1.1" in combined or "1.2" in combined

    def test_deadlock_emits_warning_log_with_dep_ids(self, tmp_path, caplog):
        """Warning log includes unsatisfied dependency IDs for each blocked task."""
        import logging

        plan = _make_plan(
            _make_task("1.1", "pending", deps=["1.2"]),
            _make_task("1.2", "pending", deps=["1.1"]),
        )
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(yaml.dump(plan))
        state = _make_state(plan_path=str(plan_file))

        with caplog.at_level(logging.WARNING, logger="langgraph_pipeline.executor.nodes.task_selector"):
            find_next_task(state)

        warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
        combined = " ".join(r.getMessage() for r in warning_records)
        # Each task's unsatisfied dep should appear somewhere in the log output
        assert "1.1" in combined and "1.2" in combined


# ─── Tests: _find_validation_pending_task ────────────────────────────────────


class TestFindValidationPendingTask:
    """_find_validation_pending_task returns first unvalidated completed task needing validation."""

    _NO_VALIDATION: dict = {}
    _VALIDATION_ENABLED: dict = {"enabled": True, "run_after": ["coder"]}

    def test_returns_none_when_validation_disabled(self):
        tasks = [_make_task("1.1", "completed")]
        assert _find_validation_pending_task(tasks, self._NO_VALIDATION) is None

    def test_returns_none_when_run_after_empty(self):
        tasks = [_make_task("1.1", "completed")]
        assert _find_validation_pending_task(tasks, {"enabled": True, "run_after": []}) is None

    def test_returns_none_when_agent_not_in_run_after(self):
        tasks = [_make_task("1.1", "completed", agent="design-judge")]
        assert _find_validation_pending_task(tasks, self._VALIDATION_ENABLED) is None

    def test_returns_none_when_already_validated(self):
        task = _make_task("1.1", "completed", agent="coder")
        task["validation_attempts"] = 1
        assert _find_validation_pending_task([task], self._VALIDATION_ENABLED) is None

    def test_returns_none_for_pending_task(self):
        tasks = [_make_task("1.1", "pending", agent="coder")]
        assert _find_validation_pending_task(tasks, self._VALIDATION_ENABLED) is None

    def test_returns_none_for_verified_task(self):
        tasks = [_make_task("1.1", "verified", agent="coder")]
        assert _find_validation_pending_task(tasks, self._VALIDATION_ENABLED) is None

    def test_returns_completed_task_needing_validation(self):
        task = _make_task("1.1", "completed", agent="coder")
        result = _find_validation_pending_task([task], self._VALIDATION_ENABLED)
        assert result is not None
        assert result["id"] == "1.1"

    def test_returns_first_task_needing_validation(self):
        task1 = _make_task("0.1", "completed", agent="coder")
        task2 = _make_task("0.2", "completed", agent="coder")
        result = _find_validation_pending_task([task1, task2], self._VALIDATION_ENABLED)
        assert result is not None
        assert result["id"] == "0.1"

    def test_skips_tasks_not_needing_validation_returns_next(self):
        task1 = _make_task("0.1", "completed", agent="design-judge")  # not in run_after
        task2 = _make_task("0.2", "completed", agent="coder")         # needs validation
        result = _find_validation_pending_task([task1, task2], self._VALIDATION_ENABLED)
        assert result is not None
        assert result["id"] == "0.2"

    def test_handles_multiple_agents_in_run_after(self):
        validation = {"enabled": True, "run_after": ["coder", "frontend-coder"]}
        task = _make_task("0.3", "completed", agent="frontend-coder")
        result = _find_validation_pending_task([task], validation)
        assert result is not None
        assert result["id"] == "0.3"

    def test_returns_none_when_all_tasks_pending(self):
        tasks = [_make_task("1.1", "pending"), _make_task("1.2", "pending")]
        assert _find_validation_pending_task(tasks, self._VALIDATION_ENABLED) is None


# ─── Tests: find_next_task validation-pending priority ───────────────────────


class TestFindNextTaskValidationPriority:
    """find_next_task prioritises validation-pending tasks over new pending work (AC1, AC7, AC8)."""

    def test_validation_pending_selected_over_pending_task(self, tmp_path):
        """AC1, AC7, AC8: unvalidated completed task takes priority over pending work."""
        validation = {"enabled": True, "run_after": ["coder"]}
        plan = _make_plan(
            _make_task("0.1", "completed", agent="coder"),  # needs validation
            _make_task("1.1", "pending"),                   # independent pending task
            validation=validation,
        )
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(yaml.dump(plan))
        state = _make_state(plan_path=str(plan_file))

        result = find_next_task(state)

        assert result["current_task_id"] == "0.1"

    def test_pending_selected_when_no_validation_pending(self, tmp_path):
        """Falls through to pending scan when all completed tasks are already validated."""
        validation = {"enabled": True, "run_after": ["coder"]}
        plan = _make_plan(
            _make_task("0.1", "verified", agent="coder"),  # already validated
            _make_task("1.1", "pending"),
            validation=validation,
        )
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(yaml.dump(plan))
        state = _make_state(plan_path=str(plan_file))

        result = find_next_task(state)

        assert result["current_task_id"] == "1.1"

    def test_reproduction_scenario_validates_parallel_task_first(self, tmp_path):
        """AC5: tasks 0.1-0.3 parallel (0.3 needs validation); 0.4 becomes ready after."""
        validation = {"enabled": True, "run_after": ["frontend-coder"]}
        plan = _make_plan(
            _make_task("0.1", "completed", agent="systems-designer"),  # no validation needed
            _make_task("0.2", "completed", agent="ux-designer"),       # no validation needed
            _make_task("0.3", "completed", agent="frontend-coder"),    # needs validation
            _make_task("0.4", "pending", deps=["0.1", "0.2", "0.3"]), # blocked until 0.3 verified
            validation=validation,
        )
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(yaml.dump(plan))
        state = _make_state(plan_path=str(plan_file))

        result = find_next_task(state)

        # 0.3 is selected for validation — not 0.4 (which is blocked) and not None (deadlock)
        assert result["current_task_id"] == "0.3"
        assert result["deadlock_detected"] is False

    def test_validation_pending_task_not_selected_when_validation_disabled(self, tmp_path):
        """Without validation config, completed tasks are promoted; pending scan runs normally."""
        plan = _make_plan(
            _make_task("0.1", "completed", agent="coder"),
            _make_task("1.1", "pending"),
        )  # no validation config
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(yaml.dump(plan))
        state = _make_state(plan_path=str(plan_file))

        result = find_next_task(state)

        assert result["current_task_id"] == "1.1"

    def test_already_validated_task_not_re_selected(self, tmp_path):
        """Tasks with validation_attempts > 0 are not re-selected for validation."""
        validation = {"enabled": True, "run_after": ["coder"]}
        plan = _make_plan(
            _make_task("0.1", "completed", agent="coder", validation_attempts=1),
            _make_task("1.1", "pending"),
            validation=validation,
        )
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(yaml.dump(plan))
        state = _make_state(plan_path=str(plan_file))

        result = find_next_task(state)

        # 0.1 already validated; 1.1 should be selected
        assert result["current_task_id"] == "1.1"


# ─── Tests: FR2 status contract (AC11, AC12, AC13) ───────────────────────────


class TestFR2StatusContract:
    """Regression safety net documenting the FR2 status contract (D3, AC11, AC12, AC13).

    Design decision D3 confirms that effective_status() and _completed_task_ids()
    already enforce the correct validation-gating contract. These tests pin that
    behavior at three layers to prevent future regressions:
      1. effective_status()       – raw status resolution
      2. _completed_task_ids()    – dependency-satisfied set building
      3. _find_eligible_task()    – task scheduling decision
    """

    _VALIDATION = {"enabled": True, "run_after": ["coder"]}

    # ── AC11: completed + agent in run_after + validation_attempts=0 → non-terminal ──

    def test_ac11_effective_status_returns_completed_for_unvalidated_task(self):
        """AC11: effective_status returns 'completed' (non-terminal) for a task awaiting validation."""
        task = {"id": "0.3", "status": "completed", "agent": "coder", "validation_attempts": 0}
        assert effective_status(task, self._VALIDATION) == "completed"

    def test_ac11_completed_task_excluded_from_completed_task_ids(self):
        """AC11: _completed_task_ids excludes a task awaiting validation from the terminal set."""
        task = _make_task("0.3", "completed", agent="coder")
        result = _completed_task_ids([task], self._VALIDATION)
        assert "0.3" not in result

    def test_ac11_dependent_blocked_when_prereq_awaits_validation(self):
        """AC11: _find_eligible_task returns None when the prerequisite is 'completed' (unvalidated)."""
        prereq = _make_task("0.3", "completed", agent="coder")
        dependent = _make_task("0.4", "pending", deps=["0.3"])
        completed = _completed_task_ids([prereq, dependent], self._VALIDATION)
        assert _find_eligible_task([dependent], completed) is None

    # ── AC12: completed + agent NOT in run_after → terminal ─────────────────────

    def test_ac12_effective_status_returns_verified_for_non_validated_agent(self):
        """AC12: effective_status returns 'verified' (terminal) when agent is not in run_after."""
        task = {"id": "0.1", "status": "completed", "agent": "systems-designer"}
        assert effective_status(task, self._VALIDATION) == "verified"

    def test_ac12_non_validated_agent_included_in_completed_task_ids(self):
        """AC12: _completed_task_ids includes a completed task whose agent is not in run_after."""
        task = _make_task("0.1", "completed", agent="systems-designer")
        result = _completed_task_ids([task], self._VALIDATION)
        assert "0.1" in result

    def test_ac12_dependent_unblocked_when_prereq_agent_not_in_run_after(self):
        """AC12: _find_eligible_task selects dependent when prerequisite agent is not validated."""
        prereq = _make_task("0.1", "completed", agent="systems-designer")
        dependent = _make_task("0.2", "pending", deps=["0.1"])
        completed = _completed_task_ids([prereq, dependent], self._VALIDATION)
        result = _find_eligible_task([dependent], completed)
        assert result is not None
        assert result["id"] == "0.2"

    # ── AC13: dependent blocked until prerequisite reaches 'verified' ────────────

    def test_ac13_dependent_blocked_while_prereq_in_completed(self):
        """AC13: _find_eligible_task returns None while prerequisite has status='completed'."""
        prereq = _make_task("0.3", "completed", agent="coder")  # awaiting validation
        dependent = _make_task("0.4", "pending", deps=["0.3"])
        completed = _completed_task_ids([prereq], self._VALIDATION)
        assert _find_eligible_task([dependent], completed) is None

    def test_ac13_dependent_unblocked_once_prereq_reaches_verified(self):
        """AC13: _find_eligible_task selects dependent after prerequisite reaches 'verified'."""
        prereq = _make_task("0.3", "verified", agent="coder")  # validation complete
        dependent = _make_task("0.4", "pending", deps=["0.3"])
        completed = _completed_task_ids([prereq], self._VALIDATION)
        result = _find_eligible_task([dependent], completed)
        assert result is not None
        assert result["id"] == "0.4"

    def test_ac13_status_transition_completed_to_verified_unblocks_dependent(self):
        """AC13: transition completed→verified changes _find_eligible_task result from None to the task."""
        dependent = _make_task("0.4", "pending", deps=["0.3"])

        # Before validation: prereq is 'completed' → dependent blocked
        prereq_before = _make_task("0.3", "completed", agent="coder")
        completed_before = _completed_task_ids([prereq_before], self._VALIDATION)
        assert _find_eligible_task([dependent], completed_before) is None

        # After validation: prereq is 'verified' → dependent unblocked
        prereq_after = _make_task("0.3", "verified", agent="coder")
        completed_after = _completed_task_ids([prereq_after], self._VALIDATION)
        result = _find_eligible_task([dependent], completed_after)
        assert result is not None
        assert result["id"] == "0.4"
