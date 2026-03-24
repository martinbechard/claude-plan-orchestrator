# tests/langgraph/executor/test_edges.py
# Unit tests for the executor conditional edge functions.
# Design: docs/plans/2026-02-26-05-task-execution-subgraph-design.md

"""Tests for langgraph_pipeline.executor.edges."""

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
