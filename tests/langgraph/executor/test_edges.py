# tests/langgraph/executor/test_edges.py
# Unit tests for the executor conditional edge functions.
# Design: docs/plans/2026-02-26-05-task-execution-subgraph-design.md

"""Tests for langgraph_pipeline.executor.edges."""

from unittest.mock import patch

from langgraph_pipeline.executor.edges import (
    DEFAULT_MAX_ATTEMPTS,
    ROUTE_ALL_DONE,
    ROUTE_CIRCUIT_BREAK,
    ROUTE_CONTINUE,
    ROUTE_FAIL,
    ROUTE_PARALLEL_GROUP,
    ROUTE_PASS,
    ROUTE_RETRY,
    ROUTE_SINGLE_TASK,
    all_done,
    circuit_check,
    parallel_check,
    retry_check,
    _tasks_completed_str,
)

# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_state(**overrides) -> dict:
    """Build a minimal TaskState dict for edge tests."""
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


def _make_plan_data(max_attempts_default=None) -> dict:
    """Build a minimal plan_data dict."""
    meta: dict = {"name": "Test Plan"}
    if max_attempts_default is not None:
        meta["max_attempts_default"] = max_attempts_default
    return {
        "meta": meta,
        "sections": [
            {
                "id": "s1",
                "tasks": [
                    {"id": "1.1", "name": "Task 1.1", "status": "pending"},
                    {
                        "id": "1.2",
                        "name": "Task 1.2",
                        "status": "pending",
                        "parallel_group": "group-a",
                    },
                ],
            }
        ],
    }


# ─── Tests: all_done ──────────────────────────────────────────────────────────


class TestAllDone:
    """all_done returns True only when current_task_id is None."""

    def test_none_task_id_is_done(self):
        state = _make_state(current_task_id=None)
        assert all_done(state) is True

    def test_task_id_set_is_not_done(self):
        state = _make_state(current_task_id="1.1")
        assert all_done(state) is False

    def test_empty_string_task_id_is_done(self):
        # Empty string is falsy; treated same as None.
        state = _make_state(current_task_id="")
        assert all_done(state) is True


# ─── Tests: parallel_check ────────────────────────────────────────────────────


class TestParallelCheck:
    """parallel_check routes to all_done, parallel_group, or single_task."""

    def test_no_current_task_routes_all_done(self):
        state = _make_state(current_task_id=None)
        assert parallel_check(state) == ROUTE_ALL_DONE

    def test_single_task_routes_single(self):
        plan_data = _make_plan_data()
        state = _make_state(current_task_id="1.1", plan_data=plan_data)
        assert parallel_check(state) == ROUTE_SINGLE_TASK

    def test_parallel_group_task_routes_parallel(self):
        plan_data = _make_plan_data()
        state = _make_state(current_task_id="1.2", plan_data=plan_data)
        assert parallel_check(state) == ROUTE_PARALLEL_GROUP

    def test_unknown_task_id_routes_single(self):
        plan_data = _make_plan_data()
        state = _make_state(current_task_id="99.99", plan_data=plan_data)
        assert parallel_check(state) == ROUTE_SINGLE_TASK

    def test_no_plan_data_routes_single_when_task_set(self):
        state = _make_state(current_task_id="1.1", plan_data=None)
        assert parallel_check(state) == ROUTE_SINGLE_TASK


# ─── Tests: circuit_check ─────────────────────────────────────────────────────


class TestCircuitCheck:
    """circuit_check opens the circuit when failure threshold is reached."""

    def test_zero_failures_routes_continue(self):
        state = _make_state(consecutive_failures=0)
        assert circuit_check(state) == ROUTE_CONTINUE

    def test_below_threshold_routes_continue(self):
        state = _make_state(consecutive_failures=2)
        assert circuit_check(state) == ROUTE_CONTINUE

    def test_at_threshold_routes_circuit_break(self):
        state = _make_state(consecutive_failures=3)
        assert circuit_check(state) == ROUTE_CIRCUIT_BREAK

    def test_above_threshold_routes_circuit_break(self):
        state = _make_state(consecutive_failures=10)
        assert circuit_check(state) == ROUTE_CIRCUIT_BREAK

    def test_none_failures_treated_as_zero(self):
        state = _make_state(consecutive_failures=None)
        assert circuit_check(state) == ROUTE_CONTINUE

    def test_quota_exhausted_routes_circuit_break(self):
        # quota_exhausted takes priority — circuit breaks even with zero failures
        state = _make_state(quota_exhausted=True, consecutive_failures=0)
        assert circuit_check(state) == ROUTE_CIRCUIT_BREAK


# ─── Tests: retry_check ───────────────────────────────────────────────────────


class TestRetryCheck:
    """retry_check routes PASS on success, RETRY or FAIL on validation failure."""

    def test_pass_verdict_routes_pass(self):
        state = _make_state(last_validation_verdict="PASS")
        assert retry_check(state) == ROUTE_PASS

    def test_warn_verdict_routes_pass(self):
        # WARN is treated as non-failure: execution continues.
        state = _make_state(last_validation_verdict="WARN")
        assert retry_check(state) == ROUTE_PASS

    def test_none_verdict_routes_pass(self):
        state = _make_state(last_validation_verdict=None)
        assert retry_check(state) == ROUTE_PASS

    def test_fail_with_attempts_remaining_routes_retry(self):
        plan_data = _make_plan_data(max_attempts_default=3)
        state = _make_state(
            last_validation_verdict="FAIL",
            task_attempt=1,
            plan_data=plan_data,
        )
        assert retry_check(state) == ROUTE_RETRY

    def test_fail_at_max_attempts_routes_fail(self):
        plan_data = _make_plan_data(max_attempts_default=3)
        state = _make_state(
            last_validation_verdict="FAIL",
            task_attempt=3,
            plan_data=plan_data,
        )
        assert retry_check(state) == ROUTE_FAIL

    def test_fail_above_max_attempts_routes_fail(self):
        plan_data = _make_plan_data(max_attempts_default=3)
        state = _make_state(
            last_validation_verdict="FAIL",
            task_attempt=5,
            plan_data=plan_data,
        )
        assert retry_check(state) == ROUTE_FAIL

    def test_fail_uses_default_when_no_plan_data(self):
        state = _make_state(
            last_validation_verdict="FAIL",
            task_attempt=DEFAULT_MAX_ATTEMPTS - 1,
            plan_data=None,
        )
        assert retry_check(state) == ROUTE_RETRY

    def test_fail_exhausted_uses_default_when_no_plan_data(self):
        state = _make_state(
            last_validation_verdict="FAIL",
            task_attempt=DEFAULT_MAX_ATTEMPTS,
            plan_data=None,
        )
        assert retry_check(state) == ROUTE_FAIL

    def test_fail_attempt_zero_routes_retry(self):
        plan_data = _make_plan_data(max_attempts_default=3)
        state = _make_state(
            last_validation_verdict="FAIL",
            task_attempt=0,
            plan_data=plan_data,
        )
        assert retry_check(state) == ROUTE_RETRY


# ─── Tests: route label constants ────────────────────────────────────────────


class TestRouteConstants:
    """Route label constants have the expected string values."""

    def test_all_done_label(self):
        assert ROUTE_ALL_DONE == "all_done"

    def test_parallel_group_label(self):
        assert ROUTE_PARALLEL_GROUP == "parallel_group"

    def test_single_task_label(self):
        assert ROUTE_SINGLE_TASK == "single_task"

    def test_circuit_break_label(self):
        assert ROUTE_CIRCUIT_BREAK == "circuit_break"

    def test_continue_label(self):
        assert ROUTE_CONTINUE == "continue"

    def test_pass_label(self):
        assert ROUTE_PASS == "pass"

    def test_retry_label(self):
        assert ROUTE_RETRY == "retry"

    def test_fail_label(self):
        assert ROUTE_FAIL == "fail"

    def test_default_max_attempts(self):
        assert DEFAULT_MAX_ATTEMPTS == 3


# ─── Tests: _tasks_completed_str ─────────────────────────────────────────────


def _make_plan_data_with_validation(
    tasks: list[dict],
    validation_enabled: bool = True,
    run_after: list[str] | None = None,
    max_attempts_default: int | None = None,
) -> dict:
    """Build plan_data with validation config and custom task list."""
    meta: dict = {"name": "Test Plan"}
    if max_attempts_default is not None:
        meta["max_attempts_default"] = max_attempts_default
    meta["validation"] = {
        "enabled": validation_enabled,
        "run_after": run_after or ["coder"],
    }
    return {
        "meta": meta,
        "sections": [{"id": "s1", "tasks": tasks}],
    }


class TestTasksCompletedStr:
    """_tasks_completed_str counts verified tasks (via effective_status) as done."""

    def test_counts_verified_tasks_as_done(self):
        plan_data = _make_plan_data_with_validation([
            {"id": "1.1", "status": "verified", "agent": "coder"},
            {"id": "1.2", "status": "pending", "agent": "coder"},
        ])
        state = _make_state(plan_data=plan_data)
        assert _tasks_completed_str(state) == "1/2"

    def test_completed_awaiting_validation_not_counted_as_done(self):
        """A task with status 'completed' that still needs validation is NOT done."""
        plan_data = _make_plan_data_with_validation([
            {"id": "1.1", "status": "completed", "agent": "coder"},
            {"id": "1.2", "status": "pending", "agent": "coder"},
        ])
        state = _make_state(plan_data=plan_data)
        assert _tasks_completed_str(state) == "0/2"

    def test_completed_promoted_via_backward_compat(self):
        """Legacy completed task with validation_attempts > 0 is promoted to verified."""
        plan_data = _make_plan_data_with_validation([
            {"id": "1.1", "status": "completed", "agent": "coder", "validation_attempts": 1},
            {"id": "1.2", "status": "pending", "agent": "coder"},
        ])
        state = _make_state(plan_data=plan_data)
        assert _tasks_completed_str(state) == "1/2"

    def test_completed_with_validation_disabled_promoted(self):
        """When validation is disabled, completed tasks are promoted to verified."""
        plan_data = _make_plan_data_with_validation(
            [
                {"id": "1.1", "status": "completed", "agent": "coder"},
                {"id": "1.2", "status": "pending", "agent": "coder"},
            ],
            validation_enabled=False,
        )
        state = _make_state(plan_data=plan_data)
        assert _tasks_completed_str(state) == "1/2"

    def test_returns_zero_when_no_tasks_verified(self):
        plan_data = _make_plan_data_with_validation([
            {"id": "1.1", "status": "pending", "agent": "coder"},
            {"id": "1.2", "status": "in_progress", "agent": "coder"},
        ])
        state = _make_state(plan_data=plan_data)
        assert _tasks_completed_str(state) == "0/2"

    def test_fallback_counts_from_task_results_when_no_plan_data(self):
        state = _make_state(
            plan_data=None,
            task_results=[{"task_id": "1.1", "status": "completed"}],
        )
        assert _tasks_completed_str(state) == "1"

    def test_fallback_counts_verified_from_task_results(self):
        state = _make_state(
            plan_data=None,
            task_results=[{"task_id": "1.1", "status": "verified"}],
        )
        assert _tasks_completed_str(state) == "1"

    def test_fallback_excludes_failed_from_task_results(self):
        state = _make_state(
            plan_data=None,
            task_results=[
                {"task_id": "1.1", "status": "completed"},
                {"task_id": "1.2", "status": "failed"},
            ],
        )
        assert _tasks_completed_str(state) == "1"

    def test_all_verified_counts_all(self):
        plan_data = _make_plan_data_with_validation([
            {"id": "1.1", "status": "verified", "agent": "coder"},
            {"id": "1.2", "status": "verified", "agent": "coder"},
        ])
        state = _make_state(plan_data=plan_data)
        assert _tasks_completed_str(state) == "2/2"


# ─── Tests: retry_check trace metadata ───────────────────────────────────────


class TestRetryCheckTraceMetadata:
    """retry_check emits pipeline_decision trace metadata on every code path."""

    def test_emits_pass_decision_on_non_fail_verdict(self):
        state = _make_state(last_validation_verdict="PASS")
        with patch("langgraph_pipeline.executor.edges.add_trace_metadata") as mock_meta:
            retry_check(state)
        mock_meta.assert_called_once()
        call_kwargs = mock_meta.call_args[0][0]
        assert call_kwargs["decision"] == "pass"
        assert call_kwargs["reason"] == "validator_passed"

    def test_emits_fail_decision_on_max_attempts_reached(self):
        plan_data = _make_plan_data(max_attempts_default=3)
        state = _make_state(
            last_validation_verdict="FAIL",
            task_attempt=3,
            plan_data=plan_data,
        )
        with patch("langgraph_pipeline.executor.edges.add_trace_metadata") as mock_meta:
            retry_check(state)
        call_kwargs = mock_meta.call_args[0][0]
        assert call_kwargs["decision"] == "fail"
        assert call_kwargs["reason"] == "max_attempts_reached"
        assert call_kwargs["cycle_number"] == 3

    def test_emits_retry_decision_with_attempts_remaining(self):
        plan_data = _make_plan_data(max_attempts_default=3)
        state = _make_state(
            last_validation_verdict="FAIL",
            task_attempt=1,
            plan_data=plan_data,
        )
        with patch("langgraph_pipeline.executor.edges.add_trace_metadata") as mock_meta:
            retry_check(state)
        call_kwargs = mock_meta.call_args[0][0]
        assert call_kwargs["decision"] == "retry"
        assert call_kwargs["reason"] == "validator_failed_retry_available"

    def test_emits_tasks_completed_string(self):
        plan_data = _make_plan_data_with_validation([
            {"id": "1.1", "status": "verified", "agent": "coder"},
            {"id": "1.2", "status": "pending", "agent": "coder"},
        ])
        state = _make_state(
            last_validation_verdict="PASS",
            plan_data=plan_data,
        )
        with patch("langgraph_pipeline.executor.edges.add_trace_metadata") as mock_meta:
            retry_check(state)
        call_kwargs = mock_meta.call_args[0][0]
        assert "tasks_completed" in call_kwargs
        assert call_kwargs["tasks_completed"] == "1/2"
