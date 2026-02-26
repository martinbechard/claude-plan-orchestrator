# tests/langgraph/pipeline/nodes/test_verification.py
# Unit tests for the verify_symptoms node.
# Design: docs/plans/2026-02-26-04-pipeline-graph-nodes-design.md

"""Tests for langgraph_pipeline.pipeline.nodes.verification."""

from unittest.mock import patch

import pytest

from langgraph_pipeline.pipeline.nodes.verification import (
    VERIFICATION_NOTES_MAX_LENGTH,
    _build_verification_record,
    _invoke_claude,
    _parse_verification_outcome,
    verify_symptoms,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_state(**overrides) -> dict:
    """Build a minimal PipelineState dict."""
    base = {
        "item_path": "docs/defect-backlog/01-bug.md",
        "item_slug": "01-bug",
        "item_type": "defect",
        "item_name": "01 Bug",
        "plan_path": ".claude/plans/01-bug.yaml",
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


# ─── _parse_verification_outcome ──────────────────────────────────────────────


class TestParseVerificationOutcome:
    def test_returns_pass_when_output_contains_pass(self):
        assert _parse_verification_outcome("Result: PASS") == "PASS"

    def test_returns_pass_case_insensitive(self):
        assert _parse_verification_outcome("result: pass") == "PASS"

    def test_returns_fail_when_output_contains_fail(self):
        assert _parse_verification_outcome("Result: FAIL") == "FAIL"

    def test_returns_fail_when_output_is_empty(self):
        assert _parse_verification_outcome("") == "FAIL"

    def test_returns_fail_when_output_has_no_keyword(self):
        assert _parse_verification_outcome("Unable to determine.") == "FAIL"

    def test_pass_takes_precedence_over_fail(self):
        # When both appear, PASS is found first by regex search
        assert _parse_verification_outcome("PASS - but it may FAIL later") == "PASS"


# ─── _build_verification_record ───────────────────────────────────────────────


class TestBuildVerificationRecord:
    def test_outcome_is_set(self):
        record = _build_verification_record("PASS", "All checks passed.")
        assert record["outcome"] == "PASS"

    def test_timestamp_is_iso_string(self):
        record = _build_verification_record("FAIL", "Tests failed.")
        ts = record["timestamp"]
        assert "T" in ts  # ISO-8601 contains T separator

    def test_notes_truncated_to_max_length(self):
        long_notes = "x" * (VERIFICATION_NOTES_MAX_LENGTH + 100)
        record = _build_verification_record("PASS", long_notes)
        assert len(record["notes"]) == VERIFICATION_NOTES_MAX_LENGTH

    def test_short_notes_not_truncated(self):
        notes = "Short notes."
        record = _build_verification_record("PASS", notes)
        assert record["notes"] == notes


# ─── _invoke_claude ───────────────────────────────────────────────────────────


class TestInvokeClaude:
    def test_returns_stdout_on_success(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = "Result: PASS\nNotes: Tests pass."
            mock_run.return_value.returncode = 0
            output = _invoke_claude("some prompt")
        assert "PASS" in output

    def test_returns_empty_string_on_timeout(self):
        import subprocess

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("claude", 300)):
            output = _invoke_claude("some prompt")
        assert output == ""

    def test_returns_empty_string_on_os_error(self):
        with patch("subprocess.run", side_effect=OSError("not found")):
            output = _invoke_claude("some prompt")
        assert output == ""


# ─── verify_symptoms node ─────────────────────────────────────────────────────


class TestVerifySymptoms:
    def test_returns_verification_history_list_with_one_record(self):
        state = _make_state()
        with patch(
            "langgraph_pipeline.pipeline.nodes.verification._invoke_claude",
            return_value="Result: PASS\nNotes: All tests pass.",
        ):
            result = verify_symptoms(state)
        assert "verification_history" in result
        assert len(result["verification_history"]) == 1

    def test_returns_pass_outcome_when_claude_says_pass(self):
        state = _make_state()
        with patch(
            "langgraph_pipeline.pipeline.nodes.verification._invoke_claude",
            return_value="Result: PASS\nNotes: Fixed.",
        ):
            result = verify_symptoms(state)
        assert result["verification_history"][0]["outcome"] == "PASS"

    def test_returns_fail_outcome_when_claude_says_fail(self):
        state = _make_state()
        with patch(
            "langgraph_pipeline.pipeline.nodes.verification._invoke_claude",
            return_value="Result: FAIL\nNotes: Tests still failing.",
        ):
            result = verify_symptoms(state)
        assert result["verification_history"][0]["outcome"] == "FAIL"

    def test_returns_fail_when_claude_returns_empty_output(self):
        state = _make_state()
        with patch(
            "langgraph_pipeline.pipeline.nodes.verification._invoke_claude",
            return_value="",
        ):
            result = verify_symptoms(state)
        assert result["verification_history"][0]["outcome"] == "FAIL"

    def test_increments_verification_cycle(self):
        state = _make_state(verification_cycle=1)
        with patch(
            "langgraph_pipeline.pipeline.nodes.verification._invoke_claude",
            return_value="Result: PASS",
        ):
            result = verify_symptoms(state)
        assert result["verification_cycle"] == 2

    def test_starts_cycle_at_one_when_zero(self):
        state = _make_state(verification_cycle=0)
        with patch(
            "langgraph_pipeline.pipeline.nodes.verification._invoke_claude",
            return_value="Result: PASS",
        ):
            result = verify_symptoms(state)
        assert result["verification_cycle"] == 1

    def test_returns_fail_when_no_item_path(self):
        state = _make_state(item_path="")
        result = verify_symptoms(state)
        assert result["verification_history"][0]["outcome"] == "FAIL"
        assert result["verification_cycle"] == 1

    def test_record_has_timestamp(self):
        state = _make_state()
        with patch(
            "langgraph_pipeline.pipeline.nodes.verification._invoke_claude",
            return_value="Result: PASS",
        ):
            result = verify_symptoms(state)
        record = result["verification_history"][0]
        assert "timestamp" in record
        assert "T" in record["timestamp"]

    def test_record_notes_set_from_claude_output(self):
        state = _make_state()
        with patch(
            "langgraph_pipeline.pipeline.nodes.verification._invoke_claude",
            return_value="Result: PASS\nNotes: Everything is working.",
        ):
            result = verify_symptoms(state)
        assert "PASS" in result["verification_history"][0]["notes"]
