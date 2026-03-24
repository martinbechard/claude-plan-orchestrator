# tests/langgraph/pipeline/test_edges.py
# Unit tests for the conditional edge routing functions.
# Design: docs/plans/2026-02-26-04-pipeline-graph-nodes-design.md

"""Tests for langgraph_pipeline.pipeline.edges."""

import pytest
from langgraph.graph import END

from langgraph_pipeline.pipeline.edges import (
    MAX_VERIFICATION_CYCLES,
    NODE_ARCHIVE,
    NODE_CREATE_PLAN,
    NODE_EXECUTE_PLAN,
    NODE_INTAKE_ANALYZE,
    NODE_VERIFY_SYMPTOMS,
    after_create_plan,
    after_intake,
    cycles_exhausted,
    has_items,
    is_defect,
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

    def test_create_plan_is_string(self):
        assert isinstance(NODE_CREATE_PLAN, str)
        assert NODE_CREATE_PLAN

    def test_verify_symptoms_is_string(self):
        assert isinstance(NODE_VERIFY_SYMPTOMS, str)
        assert NODE_VERIFY_SYMPTOMS

    def test_archive_is_string(self):
        assert isinstance(NODE_ARCHIVE, str)
        assert NODE_ARCHIVE


class TestHasItems:
    """has_items routes based on whether item_path is populated."""

    def test_returns_intake_analyze_when_item_path_set(self):
        state = _make_state(item_path="docs/defect-backlog/my-bug.md")
        assert has_items(state) == NODE_INTAKE_ANALYZE

    def test_returns_end_when_item_path_is_empty(self):
        state = _make_state(item_path="")
        assert has_items(state) == END

    def test_returns_end_when_item_path_is_none(self):
        state = _make_state(item_path=None)
        assert has_items(state) == END

    def test_returns_end_when_item_path_missing_from_state(self):
        state = {}
        assert has_items(state) == END


class TestIsDefect:
    """is_defect routes defects to verification, all others to archive."""

    def test_routes_defect_to_verify_symptoms(self):
        state = _make_state(item_type="defect")
        assert is_defect(state) == NODE_VERIFY_SYMPTOMS

    def test_routes_feature_to_archive(self):
        state = _make_state(item_type="feature")
        assert is_defect(state) == NODE_ARCHIVE

    def test_routes_analysis_to_archive(self):
        state = _make_state(item_type="analysis")
        assert is_defect(state) == NODE_ARCHIVE

    def test_routes_unknown_type_to_archive(self):
        state = _make_state(item_type="unknown")
        assert is_defect(state) == NODE_ARCHIVE

    def test_routes_missing_type_to_archive(self):
        state = {}
        assert is_defect(state) == NODE_ARCHIVE

    def test_quota_exhausted_routes_end(self):
        # quota_exhausted takes priority over item_type — item must stay on disk
        state = _make_state(item_type="defect", quota_exhausted=True)
        assert is_defect(state) == END


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


class TestAfterIntake:
    """after_intake routes to END on quota exhaustion, else create_plan."""

    def test_quota_exhausted_routes_to_end(self):
        state = _make_state(quota_exhausted=True)
        assert after_intake(state) == END

    def test_normal_state_routes_to_create_plan(self):
        state = _make_state(quota_exhausted=False)
        assert after_intake(state) == NODE_CREATE_PLAN

    def test_missing_quota_exhausted_routes_to_create_plan(self):
        state = _make_state()
        assert after_intake(state) == NODE_CREATE_PLAN


class TestAfterCreatePlan:
    """after_create_plan routes to END on quota exhaustion, else execute_plan."""

    def test_quota_exhausted_routes_to_end(self):
        state = _make_state(quota_exhausted=True)
        assert after_create_plan(state) == END

    def test_normal_state_routes_to_execute_plan(self):
        state = _make_state(quota_exhausted=False)
        assert after_create_plan(state) == NODE_EXECUTE_PLAN

    def test_missing_quota_exhausted_routes_to_execute_plan(self):
        state = _make_state()
        assert after_create_plan(state) == NODE_EXECUTE_PLAN
