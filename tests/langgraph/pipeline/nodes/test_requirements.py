# tests/langgraph/pipeline/nodes/test_requirements.py
# Unit tests for the structure_requirements LangGraph node.
# Design: docs/plans/2026-02-26-04-pipeline-graph-nodes-design.md

"""Tests for langgraph_pipeline.pipeline.nodes.requirements."""

from collections import namedtuple
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from langgraph_pipeline.pipeline.nodes.requirements import (
    MAX_VALIDATION_ITERATIONS,
    REQUIREMENTS_DIR,
    REVIEWER_MODEL,
    STRUCTURING_MODEL,
    structure_requirements,
)

# Patch targets for artifact cache functions
ARTIFACT_CACHE_MODULE = "langgraph_pipeline.pipeline.nodes.requirements"

# ─── Constants ────────────��───────────────────────────────────────────────────

MODULE = "langgraph_pipeline.pipeline.nodes.requirements"

# ─── Helpers ─────────��───────────────────────────────���────────────────────────

ClaudeResult = namedtuple("ClaudeResult", ["text", "total_cost_usd", "failure_reason", "raw_stdout", "input_tokens", "output_tokens"])


def _make_state(**overrides) -> dict:
    """Build a minimal PipelineState dict for testing."""
    base = {
        "item_path": "/tmp/test-item.md",
        "item_slug": "01-test-feature",
        "item_type": "feature",
        "item_name": "01 Test Feature",
        "requirements_path": None,
        "plan_path": None,
        "design_doc_path": None,
        "workspace_path": None,
        "clause_register_path": None,
        "five_whys_path": None,
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


def _success_result(text: str, cost: float = 0.05) -> ClaudeResult:
    return ClaudeResult(
        text=text,
        total_cost_usd=cost,
        failure_reason=None,
        raw_stdout=text,
        input_tokens=100,
        output_tokens=200,
    )


def _failure_result(reason: str) -> ClaudeResult:
    return ClaudeResult(
        text="",
        total_cost_usd=0.0,
        failure_reason=reason,
        raw_stdout="",
        input_tokens=0,
        output_tokens=0,
    )


STRUCTURED_OUTPUT = (
    "### P1: Fix the button\n"
    "Type: UI\n"
    "Priority: high\n"
    "Description: The submit button does not work on mobile.\n"
    "Acceptance Criteria:\n"
    "- Does the button work on mobile? YES = pass, NO = fail\n\n"
    "## Coverage Matrix\n"
    "| Raw Input Section | Requirement(s) |\n"
    "|---|---|\n"
    '| "button broken on mobile" | P1 |\n'
)


# ─── Tests ─────────────���───────────────────────��──────────────────────────────


class TestShortCircuit:
    """structure_requirements short-circuits on existing requirements or plan."""

    def test_returns_empty_when_requirements_path_exists(self, tmp_path):
        req_file = tmp_path / "requirements.md"
        req_file.write_text("existing requirements")
        state = _make_state(requirements_path=str(req_file))
        result = structure_requirements(state)
        assert result == {}

    def test_returns_empty_when_plan_path_set(self):
        state = _make_state(plan_path="tmp/plans/existing.yaml")
        result = structure_requirements(state)
        assert result == {}


class TestNoItemFile:
    """structure_requirements returns empty dict when item file cannot be read."""

    def test_returns_empty_when_item_path_missing(self):
        state = _make_state(item_path="/nonexistent/path.md")
        result = structure_requirements(state)
        assert result == {}


class TestSuccessfulStructuring:
    """structure_requirements creates a requirements file on successful structuring + review."""

    @patch(f"{MODULE}.call_claude")
    @patch(f"{MODULE}.detect_quota_exhaustion", return_value=False)
    @patch(f"{MODULE}.add_trace_metadata")
    def test_creates_requirements_file_on_accept(self, mock_trace, mock_quota, mock_claude, tmp_path):
        # Setup: item file exists
        item_file = tmp_path / "item.md"
        item_file.write_text("Fix the button on mobile. It does not work.")

        # Mock: first call = structuring (Opus), second call = reviewer (Haiku) ACCEPT
        mock_claude.side_effect = [
            _success_result(STRUCTURED_OUTPUT, 0.10),
            _success_result("ACCEPT", 0.01),
        ]

        # Setup output dir
        req_dir = tmp_path / "docs" / "plans"
        with patch(f"{MODULE}.REQUIREMENTS_DIR", str(req_dir)):
            state = _make_state(item_path=str(item_file), item_slug="test-button")
            result = structure_requirements(state)

        assert "requirements_path" in result
        assert result["requirements_path"].endswith("-requirements.md")

        # Verify the file was written
        req_file = Path(result["requirements_path"])
        assert req_file.exists()
        content = req_file.read_text()
        assert "P1: Fix the button" in content
        assert "Status: ACCEPTED" in content
        assert "Coverage Matrix" in content


class TestRejectionAndRetry:
    """structure_requirements retries on REJECT from reviewer."""

    @patch(f"{MODULE}.call_claude")
    @patch(f"{MODULE}.detect_quota_exhaustion", return_value=False)
    @patch(f"{MODULE}.add_trace_metadata")
    def test_retries_on_reject_then_accepts(self, mock_trace, mock_quota, mock_claude, tmp_path):
        item_file = tmp_path / "item.md"
        item_file.write_text("Fix button on mobile. Also fix the color.")

        improved_output = STRUCTURED_OUTPUT + "\n### P2: Fix the color\nType: UI\nPriority: medium\nDescription: Fix color.\n"

        # Call sequence: structure -> review(REJECT) -> retry structure -> review(ACCEPT)
        mock_claude.side_effect = [
            _success_result(STRUCTURED_OUTPUT, 0.10),             # Initial structuring
            _success_result("REJECT\n- Missing color fix requirement", 0.01),  # Review REJECT
            _success_result(improved_output, 0.10),               # Retry structuring
            _success_result("ACCEPT", 0.01),                      # Review ACCEPT
        ]

        req_dir = tmp_path / "docs" / "plans"
        with patch(f"{MODULE}.REQUIREMENTS_DIR", str(req_dir)):
            state = _make_state(item_path=str(item_file), item_slug="test-button-retry")
            result = structure_requirements(state)

        assert "requirements_path" in result
        content = Path(result["requirements_path"]).read_text()
        assert "Iterations: 2" in content


class TestQuotaExhaustion:
    """structure_requirements returns quota_exhausted on quota detection."""

    @patch(f"{MODULE}.call_claude")
    @patch(f"{MODULE}.detect_quota_exhaustion", return_value=True)
    def test_returns_quota_exhausted_on_structuring_failure(self, mock_quota, mock_claude):
        mock_claude.return_value = _failure_result("quota exhausted")
        state = _make_state(item_path="/tmp/test.md")
        with patch(f"{MODULE}._read_file_content", return_value="some content"):
            result = structure_requirements(state)
        assert result == {"quota_exhausted": True}


class TestMaxIterations:
    """structure_requirements stops after MAX_VALIDATION_ITERATIONS rejections."""

    @patch(f"{MODULE}.call_claude")
    @patch(f"{MODULE}.detect_quota_exhaustion", return_value=False)
    @patch(f"{MODULE}.add_trace_metadata")
    def test_accepts_after_max_iterations(self, mock_trace, mock_quota, mock_claude, tmp_path):
        item_file = tmp_path / "item.md"
        item_file.write_text("Test item content.")

        # Build call sequence: structure, then for each iteration: review(REJECT), retry structure
        # Final iteration just reviews and accepts at max
        calls = [_success_result(STRUCTURED_OUTPUT, 0.10)]  # Initial structuring
        for i in range(MAX_VALIDATION_ITERATIONS):
            calls.append(_success_result(f"REJECT\n- Missing item {i}", 0.01))  # Review rejects
            if i < MAX_VALIDATION_ITERATIONS - 1:
                calls.append(_success_result(STRUCTURED_OUTPUT, 0.10))  # Retry

        mock_claude.side_effect = calls

        req_dir = tmp_path / "docs" / "plans"
        with patch(f"{MODULE}.REQUIREMENTS_DIR", str(req_dir)):
            state = _make_state(item_path=str(item_file), item_slug="test-max-iter")
            result = structure_requirements(state)

        # Should still produce a file even at max iterations
        assert "requirements_path" in result
        content = Path(result["requirements_path"]).read_text()
        assert "Max iterations reached" in content


class TestFreshnessSkip:
    """structure_requirements skips when workspace artifact is fresh."""

    @patch(f"{MODULE}.is_artifact_fresh", return_value=True)
    def test_skips_when_fresh_and_existing_file_found(self, mock_fresh, tmp_path):
        req_file = tmp_path / "docs" / "plans" / f"2026-01-01-test-slug-requirements.md"
        req_file.parent.mkdir(parents=True)
        req_file.write_text("existing requirements")

        state = _make_state(
            item_slug="test-slug",
            workspace_path=str(tmp_path / "workspace"),
            clause_register_path=str(tmp_path / "clauses.md"),
            five_whys_path=str(tmp_path / "five-whys.md"),
        )
        with patch(f"{MODULE}.REQUIREMENTS_DIR", str(tmp_path / "docs" / "plans")):
            result = structure_requirements(state)

        assert "requirements_path" in result
        assert result["requirements_path"].endswith("-requirements.md")
        mock_fresh.assert_called_once()

    @patch(f"{MODULE}.is_artifact_fresh", return_value=True)
    def test_does_not_skip_when_no_existing_file(self, mock_fresh, tmp_path):
        """If workspace is fresh but no docs/plans file exists, re-runs the step."""
        state = _make_state(
            item_slug="test-slug",
            workspace_path=str(tmp_path / "workspace"),
            clause_register_path=str(tmp_path / "clauses.md"),
            five_whys_path=str(tmp_path / "five-whys.md"),
        )
        with patch(f"{MODULE}.REQUIREMENTS_DIR", str(tmp_path / "docs" / "plans")):
            # No requirements file in docs/plans — should fall through to normal execution
            # (which will fail because item_path doesn't exist, returning empty dict)
            result = structure_requirements(state)

        assert result == {}  # item_path doesn't exist, so returns empty

    @patch(f"{MODULE}.is_artifact_fresh", return_value=False)
    @patch(f"{MODULE}.call_claude")
    @patch(f"{MODULE}.detect_quota_exhaustion", return_value=False)
    @patch(f"{MODULE}.add_trace_metadata")
    def test_reruns_when_stale(self, mock_trace, mock_quota, mock_claude, mock_fresh, tmp_path):
        """When is_artifact_fresh returns False, the LLM step executes normally."""
        item_file = tmp_path / "item.md"
        item_file.write_text("Fix something important.")

        mock_claude.side_effect = [
            _success_result(STRUCTURED_OUTPUT, 0.10),
            _success_result("ACCEPT", 0.01),
        ]

        req_dir = tmp_path / "docs" / "plans"
        state = _make_state(
            item_path=str(item_file),
            item_slug="stale-slug",
            workspace_path=str(tmp_path / "workspace"),
            clause_register_path=str(tmp_path / "clauses.md"),
            five_whys_path=str(tmp_path / "five-whys.md"),
        )
        with patch(f"{MODULE}.REQUIREMENTS_DIR", str(req_dir)):
            result = structure_requirements(state)

        assert "requirements_path" in result
        mock_claude.assert_called()  # LLM was invoked because stale

    def test_skips_freshness_check_when_workspace_path_absent(self):
        """No freshness check when workspace_path is not in state."""
        state = _make_state(item_path="/nonexistent/item.md")
        # workspace_path absent → falls through to item read → returns empty (no item file)
        result = structure_requirements(state)
        assert result == {}

    def test_skips_freshness_check_when_clause_register_absent(self, tmp_path):
        """Freshness check requires both clause_register_path and five_whys_path."""
        state = _make_state(
            item_path="/nonexistent/item.md",
            workspace_path=str(tmp_path),
            five_whys_path=str(tmp_path / "five-whys.md"),
        )
        # clause_register_path absent → no freshness check → returns empty (no item file)
        result = structure_requirements(state)
        assert result == {}

    @patch(f"{MODULE}.record_artifact")
    @patch(f"{MODULE}.is_artifact_fresh", return_value=False)
    @patch(f"{MODULE}.call_claude")
    @patch(f"{MODULE}.detect_quota_exhaustion", return_value=False)
    @patch(f"{MODULE}.add_trace_metadata")
    def test_records_artifact_after_producing_requirements(
        self, mock_trace, mock_quota, mock_claude, mock_fresh, mock_record, tmp_path
    ):
        """record_artifact is called with workspace, output name, and input paths."""
        item_file = tmp_path / "item.md"
        item_file.write_text("Fix the widget.")
        clauses = tmp_path / "clauses.md"
        five_whys = tmp_path / "five-whys.md"

        mock_claude.side_effect = [
            _success_result(STRUCTURED_OUTPUT, 0.10),
            _success_result("ACCEPT", 0.01),
        ]

        req_dir = tmp_path / "docs" / "plans"
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        state = _make_state(
            item_path=str(item_file),
            item_slug="record-test",
            workspace_path=str(workspace),
            clause_register_path=str(clauses),
            five_whys_path=str(five_whys),
        )
        with patch(f"{MODULE}.REQUIREMENTS_DIR", str(req_dir)):
            structure_requirements(state)

        mock_record.assert_called_once_with(
            str(workspace), "requirements.md", [str(clauses), str(five_whys)]
        )


class TestConstants:
    """Verify module constants are reasonable."""

    def test_max_validation_iterations_is_positive(self):
        assert MAX_VALIDATION_ITERATIONS > 0

    def test_structuring_model_is_opus(self):
        assert "opus" in STRUCTURING_MODEL

    def test_reviewer_model_is_haiku(self):
        assert "haiku" in REVIEWER_MODEL
