# tests/langgraph/pipeline/test_state.py
# Unit tests for the PipelineState schema and related types.
# Design: docs/plans/2026-02-26-04-pipeline-graph-nodes-design.md

"""Tests for langgraph_pipeline.pipeline.state."""

import operator
from typing import get_type_hints

import pytest

from langgraph_pipeline.pipeline.state import (
    ItemType,
    PipelineState,
    VerificationOutcome,
    VerificationRecord,
)


class TestItemType:
    """ItemType literal covers the three backlog categories."""

    def test_defect_is_valid(self):
        value: ItemType = "defect"
        assert value == "defect"

    def test_feature_is_valid(self):
        value: ItemType = "feature"
        assert value == "feature"

    def test_analysis_is_valid(self):
        value: ItemType = "analysis"
        assert value == "analysis"


class TestVerificationOutcome:
    """VerificationOutcome literal covers PASS and FAIL."""

    def test_pass_is_valid(self):
        value: VerificationOutcome = "PASS"
        assert value == "PASS"

    def test_fail_is_valid(self):
        value: VerificationOutcome = "FAIL"
        assert value == "FAIL"


class TestVerificationRecord:
    """VerificationRecord is a TypedDict with the expected keys."""

    def test_required_keys_present(self):
        hints = get_type_hints(VerificationRecord)
        assert "outcome" in hints
        assert "timestamp" in hints
        assert "notes" in hints

    def test_can_construct_valid_record(self):
        record: VerificationRecord = {
            "outcome": "PASS",
            "timestamp": "2026-02-26T00:00:00Z",
            "notes": "All assertions succeeded",
        }
        assert record["outcome"] == "PASS"

    def test_can_construct_fail_record(self):
        record: VerificationRecord = {
            "outcome": "FAIL",
            "timestamp": "2026-02-26T01:00:00Z",
            "notes": "Symptom still reproducible",
        }
        assert record["outcome"] == "FAIL"


class TestPipelineStateKeys:
    """PipelineState TypedDict declares the full set of expected fields."""

    def _hints(self):
        return get_type_hints(PipelineState, include_extras=True)

    def test_item_metadata_fields_present(self):
        hints = self._hints()
        assert "item_path" in hints
        assert "item_slug" in hints
        assert "item_type" in hints
        assert "item_name" in hints

    def test_plan_fields_present(self):
        hints = self._hints()
        assert "plan_path" in hints
        assert "design_doc_path" in hints

    def test_verification_fields_present(self):
        hints = self._hints()
        assert "verification_cycle" in hints
        assert "verification_history" in hints

    def test_control_flag_fields_present(self):
        hints = self._hints()
        assert "should_stop" in hints
        assert "rate_limited" in hints
        assert "rate_limit_reset" in hints

    def test_cost_tracking_fields_present(self):
        hints = self._hints()
        assert "session_cost_usd" in hints
        assert "session_input_tokens" in hints
        assert "session_output_tokens" in hints

    def test_intake_counter_fields_present(self):
        hints = self._hints()
        assert "intake_count_defects" in hints
        assert "intake_count_features" in hints


class TestVerificationHistoryReducer:
    """verification_history uses operator.add so LangGraph appends instead of replacing."""

    def test_reducer_is_operator_add(self):
        hints = get_type_hints(PipelineState, include_extras=True)
        annotation = hints["verification_history"]
        # Annotated stores metadata as __metadata__; the reducer should be operator.add
        metadata = annotation.__metadata__
        assert operator.add in metadata

    def test_operator_add_merges_lists(self):
        """Verify operator.add behaves as expected for list accumulation."""
        existing: list[VerificationRecord] = [
            {"outcome": "FAIL", "timestamp": "t1", "notes": ""}
        ]
        new_record: list[VerificationRecord] = [
            {"outcome": "PASS", "timestamp": "t2", "notes": ""}
        ]
        merged = operator.add(existing, new_record)
        assert len(merged) == 2
        assert merged[0]["outcome"] == "FAIL"
        assert merged[1]["outcome"] == "PASS"
