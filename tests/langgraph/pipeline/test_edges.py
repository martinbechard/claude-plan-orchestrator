# tests/langgraph/pipeline/test_edges.py
# Unit tests for the conditional edge routing functions.
# Design: docs/plans/2026-02-26-04-pipeline-graph-nodes-design.md

"""Tests for langgraph_pipeline.pipeline.edges."""

import pytest
from unittest.mock import patch
from langgraph.graph import END

from langgraph_pipeline.pipeline.edges import (
    MAX_VERIFICATION_CYCLES,
    NODE_ARCHIVE,
    NODE_CREATE_PLAN,
    NODE_EXECUTE_PLAN,
    NODE_INTAKE_ANALYZE,
    NODE_PROCESS_INVESTIGATION,
    NODE_RUN_INVESTIGATION,
    NODE_STRUCTURE_REQS,
    NODE_VERIFY_FIX,
    cycles_exhausted,
    route_after_execution,
    route_after_intake,
    route_after_investigation,
    route_after_plan,
    route_after_process_investigation,
    route_after_requirements,
    verify_result,
)


def _make_state(**overrides) -> dict:
    """Build a minimal state dict with sensible defaults, overriding as needed."""
    base = {
        "item_path": "",
        "item_slug": "",
        "item_type": "feature",
        "item_name": "",
        "plan_path": None,
        "design_doc_path": None,
        "verification_cycle": 0,
        "verification_history": [],
        "should_stop": False,
        "rate_limited": False,
        "rate_limit_reset": None,
        "session_cost_usd": 0.0,
        "session_input_tokens": 0,
        "session_output_tokens": 0,
        "intake_count_defects": 0,
        "intake_count_features": 0,
    }
    base.update(overrides)
    return base


class TestMaxVerificationCycles:
    def test_is_positive_integer(self):
        assert isinstance(MAX_VERIFICATION_CYCLES, int)
        assert MAX_VERIFICATION_CYCLES > 0

    def test_default_value(self):
        assert MAX_VERIFICATION_CYCLES == 3


class TestNodeNameConstants:
    """Node name constants must be non-empty strings."""

    def test_intake_analyze_is_string(self):
        assert isinstance(NODE_INTAKE_ANALYZE, str)
        assert NODE_INTAKE_ANALYZE

    def test_structure_reqs_is_string(self):
        assert isinstance(NODE_STRUCTURE_REQS, str)
        assert NODE_STRUCTURE_REQS

    def test_create_plan_is_string(self):
        assert isinstance(NODE_CREATE_PLAN, str)
        assert NODE_CREATE_PLAN

    def test_verify_fix_is_string(self):
        assert isinstance(NODE_VERIFY_FIX, str)
        assert NODE_VERIFY_FIX

    def test_archive_is_string(self):
        assert isinstance(NODE_ARCHIVE, str)
        assert NODE_ARCHIVE


class TestRouteAfterExecution:
    """route_after_execution routes defects to verification, all others to archive."""

    def test_routes_defect_to_verify_fix(self):
        state = _make_state(item_type="defect")
        assert route_after_execution(state) == NODE_VERIFY_FIX

    def test_routes_feature_to_archive(self):
        state = _make_state(item_type="feature")
        assert route_after_execution(state) == NODE_ARCHIVE

    def test_routes_analysis_to_archive(self):
        state = _make_state(item_type="analysis")
        assert route_after_execution(state) == NODE_ARCHIVE

    def test_routes_unknown_type_to_archive(self):
        state = _make_state(item_type="unknown")
        assert route_after_execution(state) == NODE_ARCHIVE

    def test_routes_missing_type_to_archive(self):
        state = {}
        assert route_after_execution(state) == NODE_ARCHIVE

    def test_quota_exhausted_routes_end(self):
        # quota_exhausted takes priority over item_type — item must stay on disk
        state = _make_state(item_type="defect", quota_exhausted=True)
        assert route_after_execution(state) == END

    def test_deadlock_routes_defect_to_archive(self):
        # Deadlock bypasses verification — tasks never ran so there is nothing to verify.
        state = _make_state(item_type="defect", executor_deadlock=True)
        assert route_after_execution(state) == NODE_ARCHIVE

    def test_deadlock_routes_feature_to_archive(self):
        state = _make_state(item_type="feature", executor_deadlock=True)
        assert route_after_execution(state) == NODE_ARCHIVE

    def test_deadlock_with_details_routes_to_archive(self):
        details = [{"task_id": "0.4", "task_name": "T", "unsatisfied_deps": ["0.3"]}]
        state = _make_state(
            item_type="defect",
            executor_deadlock=True,
            executor_deadlock_details=details,
        )
        assert route_after_execution(state) == NODE_ARCHIVE

    def test_quota_exhausted_takes_priority_over_deadlock(self):
        # quota_exhausted must keep the item on disk regardless of deadlock.
        state = _make_state(item_type="defect", quota_exhausted=True, executor_deadlock=True)
        assert route_after_execution(state) == END

    def test_deadlock_false_does_not_affect_routing(self):
        state = _make_state(item_type="defect", executor_deadlock=False)
        assert route_after_execution(state) == NODE_VERIFY_FIX


class TestCyclesExhausted:
    """cycles_exhausted returns True only when verification_cycle >= MAX."""

    def test_false_when_cycle_is_zero(self):
        state = _make_state(verification_cycle=0)
        assert cycles_exhausted(state) is False

    def test_false_when_cycle_is_below_max(self):
        state = _make_state(verification_cycle=MAX_VERIFICATION_CYCLES - 1)
        assert cycles_exhausted(state) is False

    def test_true_when_cycle_equals_max(self):
        state = _make_state(verification_cycle=MAX_VERIFICATION_CYCLES)
        assert cycles_exhausted(state) is True

    def test_true_when_cycle_exceeds_max(self):
        state = _make_state(verification_cycle=MAX_VERIFICATION_CYCLES + 5)
        assert cycles_exhausted(state) is True

    def test_false_when_cycle_missing_from_state(self):
        state = {}
        assert cycles_exhausted(state) is False


class TestVerifyResult:
    """verify_result routes based on last outcome and remaining cycle budget."""

    def _record(self, outcome: str) -> dict:
        return {"outcome": outcome, "timestamp": "2026-02-26T00:00:00Z", "notes": ""}

    def test_returns_archive_when_history_empty(self):
        state = _make_state(verification_history=[], verification_cycle=0)
        assert verify_result(state) == NODE_ARCHIVE

    def test_returns_archive_on_pass(self):
        state = _make_state(
            verification_history=[self._record("PASS")],
            verification_cycle=1,
        )
        assert verify_result(state) == NODE_ARCHIVE

    def test_returns_create_plan_on_fail_with_cycles_remaining(self):
        state = _make_state(
            verification_history=[self._record("FAIL")],
            verification_cycle=1,  # below MAX_VERIFICATION_CYCLES
        )
        assert verify_result(state) == NODE_CREATE_PLAN

    def test_returns_archive_on_fail_with_cycles_exhausted(self):
        state = _make_state(
            verification_history=[self._record("FAIL")],
            verification_cycle=MAX_VERIFICATION_CYCLES,
        )
        assert verify_result(state) == NODE_ARCHIVE

    def test_uses_last_record_in_history(self):
        """Only the most recent outcome governs routing."""
        state = _make_state(
            verification_history=[self._record("FAIL"), self._record("PASS")],
            verification_cycle=2,
        )
        assert verify_result(state) == NODE_ARCHIVE

    def test_fail_then_fail_with_cycle_left_routes_to_create_plan(self):
        state = _make_state(
            verification_history=[self._record("PASS"), self._record("FAIL")],
            verification_cycle=1,
        )
        assert verify_result(state) == NODE_CREATE_PLAN

    def test_returns_archive_when_history_missing_from_state(self):
        state = {}
        assert verify_result(state) == NODE_ARCHIVE


class TestVerifyResultTraceMetadata:
    """verify_result emits pipeline_decision trace metadata on every code path."""

    def _record(self, outcome: str) -> dict:
        return {"outcome": outcome, "timestamp": "2026-02-26T00:00:00Z", "notes": ""}

    def test_emits_archive_reason_no_history(self):
        state = _make_state(verification_history=[], verification_cycle=0)
        with patch("langgraph_pipeline.pipeline.edges.add_trace_metadata") as mock_meta:
            verify_result(state)
        mock_meta.assert_called_once()
        call_kwargs = mock_meta.call_args[0][0]
        assert call_kwargs["decision"] == "archive"
        assert call_kwargs["reason"] == "no_verification_history"
        assert call_kwargs["cycle_number"] == 0

    def test_emits_archive_reason_validator_passed(self):
        state = _make_state(
            verification_history=[self._record("PASS")],
            verification_cycle=1,
        )
        with patch("langgraph_pipeline.pipeline.edges.add_trace_metadata") as mock_meta:
            verify_result(state)
        call_kwargs = mock_meta.call_args[0][0]
        assert call_kwargs["decision"] == "archive"
        assert call_kwargs["reason"] == "validator_passed"
        assert call_kwargs["cycle_number"] == 1

    def test_emits_archive_reason_max_cycles_reached(self):
        state = _make_state(
            verification_history=[self._record("FAIL")],
            verification_cycle=MAX_VERIFICATION_CYCLES,
        )
        with patch("langgraph_pipeline.pipeline.edges.add_trace_metadata") as mock_meta:
            verify_result(state)
        call_kwargs = mock_meta.call_args[0][0]
        assert call_kwargs["decision"] == "archive"
        assert call_kwargs["reason"] == "max_verification_cycles_reached"

    def test_emits_retry_reason_validator_failed(self):
        state = _make_state(
            verification_history=[self._record("FAIL")],
            verification_cycle=1,
        )
        with patch("langgraph_pipeline.pipeline.edges.add_trace_metadata") as mock_meta:
            verify_result(state)
        call_kwargs = mock_meta.call_args[0][0]
        assert call_kwargs["decision"] == "retry"
        assert call_kwargs["reason"] == "validator_failed_retrying"

    def test_tasks_completed_format_includes_cycle_of_max(self):
        state = _make_state(
            verification_history=[self._record("PASS")],
            verification_cycle=2,
        )
        with patch("langgraph_pipeline.pipeline.edges.add_trace_metadata") as mock_meta:
            verify_result(state)
        call_kwargs = mock_meta.call_args[0][0]
        assert call_kwargs["tasks_completed"] == f"2/{MAX_VERIFICATION_CYCLES}"


class TestRouteAfterIntake:
    """route_after_intake routes to END on quota exhaustion, else structure_requirements."""

    def test_quota_exhausted_routes_to_end(self):
        state = _make_state(quota_exhausted=True)
        assert route_after_intake(state) == END

    def test_normal_state_routes_to_structure_requirements(self):
        state = _make_state(quota_exhausted=False)
        assert route_after_intake(state) == NODE_STRUCTURE_REQS

    def test_missing_quota_exhausted_routes_to_structure_requirements(self):
        state = _make_state()
        assert route_after_intake(state) == NODE_STRUCTURE_REQS


class TestRouteAfterRequirements:
    """route_after_requirements routes to END on quota/failure, else create_plan."""

    def test_quota_exhausted_routes_to_end(self):
        state = _make_state(quota_exhausted=True)
        assert route_after_requirements(state) == END

    def test_normal_state_routes_to_create_plan(self):
        state = _make_state(requirements_path="docs/plans/2026-03-28-test-requirements.md")
        assert route_after_requirements(state) == NODE_CREATE_PLAN

    def test_no_requirements_path_routes_to_end(self):
        state = _make_state(requirements_path=None)
        assert route_after_requirements(state) == END

    def test_empty_requirements_path_routes_to_end(self):
        state = _make_state(requirements_path="")
        assert route_after_requirements(state) == END


class TestRouteAfterPlan:
    """route_after_plan routes to END on quota exhaustion, else execute_plan."""

    def test_quota_exhausted_routes_to_end(self):
        state = _make_state(quota_exhausted=True)
        assert route_after_plan(state) == END

    def test_normal_state_routes_to_execute_plan(self):
        state = _make_state(quota_exhausted=False, plan_path="tmp/plans/test.yaml")
        assert route_after_plan(state) == NODE_EXECUTE_PLAN

    def test_missing_quota_exhausted_routes_to_execute_plan(self):
        state = _make_state(plan_path="tmp/plans/test.yaml")
        assert route_after_plan(state) == NODE_EXECUTE_PLAN

    def test_no_plan_path_routes_to_end(self):
        state = _make_state(quota_exhausted=False, plan_path=None)
        assert route_after_plan(state) == END


class TestRouteAfterIntakeInvestigation:
    """route_after_intake diverges investigation items to run_investigation."""

    def test_investigation_routes_to_run_investigation(self):
        state = _make_state(item_type="investigation")
        assert route_after_intake(state) == NODE_RUN_INVESTIGATION

    def test_investigation_with_quota_exhausted_routes_to_end(self):
        state = _make_state(item_type="investigation", quota_exhausted=True)
        assert route_after_intake(state) == END

    def test_feature_still_routes_to_structure_requirements(self):
        state = _make_state(item_type="feature")
        assert route_after_intake(state) == NODE_STRUCTURE_REQS

    def test_defect_still_routes_to_structure_requirements(self):
        state = _make_state(item_type="defect")
        assert route_after_intake(state) == NODE_STRUCTURE_REQS

    def test_analysis_still_routes_to_structure_requirements(self):
        state = _make_state(item_type="analysis")
        assert route_after_intake(state) == NODE_STRUCTURE_REQS


class TestRouteAfterInvestigation:
    """route_after_investigation always routes to process_investigation."""

    def test_routes_to_process_investigation(self):
        state = _make_state(item_type="investigation")
        assert route_after_investigation(state) == NODE_PROCESS_INVESTIGATION

    def test_routes_to_process_investigation_regardless_of_should_stop(self):
        state = _make_state(item_type="investigation", should_stop=True)
        assert route_after_investigation(state) == NODE_PROCESS_INVESTIGATION

    def test_routes_to_process_investigation_with_empty_state(self):
        assert route_after_investigation({}) == NODE_PROCESS_INVESTIGATION


class TestRouteAfterProcessInvestigation:
    """route_after_process_investigation returns END when suspended, else archive."""

    def test_should_stop_true_routes_to_end(self):
        state = _make_state(item_type="investigation", should_stop=True)
        assert route_after_process_investigation(state) == END

    def test_should_stop_false_routes_to_archive(self):
        state = _make_state(item_type="investigation", should_stop=False)
        assert route_after_process_investigation(state) == NODE_ARCHIVE

    def test_missing_should_stop_routes_to_archive(self):
        state = _make_state(item_type="investigation")
        assert route_after_process_investigation(state) == NODE_ARCHIVE

    def test_empty_state_routes_to_archive(self):
        assert route_after_process_investigation({}) == NODE_ARCHIVE
