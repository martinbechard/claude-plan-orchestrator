# tests/langgraph/pipeline/nodes/test_archival.py
# Unit tests for the archive node.
# Design: docs/plans/2026-02-26-04-pipeline-graph-nodes-design.md

"""Tests for langgraph_pipeline.pipeline.nodes.archival."""

import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from langgraph_pipeline.pipeline.nodes.archival import (
    ARCHIVE_OUTCOME_EXHAUSTED,
    ARCHIVE_OUTCOME_SUCCESS,
    _build_slack_message,
    _determine_outcome,
    _last_verification_outcome,
    _move_item_to_completed,
    _remove_plan_yaml,
    _strip_trace_id_line,
    archive,
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
        "verification_cycle": 1,
        "verification_history": [
            {"outcome": "PASS", "timestamp": "2026-01-01T00:00:00+00:00", "notes": "Fixed."}
        ],
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


def _make_defect_fail_state(cycle: int = 3) -> dict:
    """State for a defect that failed verification and exhausted cycles."""
    return _make_state(
        item_type="defect",
        verification_cycle=cycle,
        verification_history=[
            {"outcome": "FAIL", "timestamp": "2026-01-01T00:00:00+00:00", "notes": "Still broken."}
        ],
    )


# ─── _last_verification_outcome ───────────────────────────────────────────────


class TestLastVerificationOutcome:
    def test_returns_none_when_history_empty(self):
        state = _make_state(verification_history=[])
        assert _last_verification_outcome(state) is None

    def test_returns_pass_outcome(self):
        state = _make_state()  # default has PASS
        assert _last_verification_outcome(state) == "PASS"

    def test_returns_fail_outcome(self):
        state = _make_defect_fail_state()
        assert _last_verification_outcome(state) == "FAIL"

    def test_returns_last_when_multiple_records(self):
        state = _make_state(
            verification_history=[
                {"outcome": "FAIL", "timestamp": "2026-01-01T00:00:00+00:00", "notes": ""},
                {"outcome": "PASS", "timestamp": "2026-01-02T00:00:00+00:00", "notes": ""},
            ]
        )
        assert _last_verification_outcome(state) == "PASS"


# ─── _determine_outcome ───────────────────────────────────────────────────────


class TestDetermineOutcome:
    def test_feature_is_always_success(self):
        state = _make_state(
            item_type="feature",
            verification_history=[],
        )
        assert _determine_outcome(state) == ARCHIVE_OUTCOME_SUCCESS

    def test_analysis_is_always_success(self):
        state = _make_state(
            item_type="analysis",
            verification_history=[],
        )
        assert _determine_outcome(state) == ARCHIVE_OUTCOME_SUCCESS

    def test_defect_with_pass_is_success(self):
        state = _make_state(item_type="defect")  # has PASS record
        assert _determine_outcome(state) == ARCHIVE_OUTCOME_SUCCESS

    def test_defect_with_fail_is_exhausted(self):
        state = _make_defect_fail_state()
        assert _determine_outcome(state) == ARCHIVE_OUTCOME_EXHAUSTED

    def test_defect_with_no_history_is_success(self):
        state = _make_state(item_type="defect", verification_history=[])
        assert _determine_outcome(state) == ARCHIVE_OUTCOME_SUCCESS


# ─── _move_item_to_completed ──────────────────────────────────────────────────


class TestMoveItemToCompleted:
    def test_moves_file_to_completed_dir(self, tmp_path):
        src_file = tmp_path / "01-bug.md"
        src_file.write_text("# Bug")

        dest_dir = tmp_path / "completed" / "defects"

        with patch(
            "langgraph_pipeline.pipeline.nodes.archival.COMPLETED_DIRS",
            {"defect": str(dest_dir)},
        ):
            result = _move_item_to_completed(str(src_file), "defect")

        assert result is not None
        assert Path(result).exists()
        assert not src_file.exists()

    def test_returns_none_when_source_missing(self, tmp_path):
        result = _move_item_to_completed(str(tmp_path / "nonexistent.md"), "defect")
        assert result is None

    def test_creates_destination_directory(self, tmp_path):
        src_file = tmp_path / "01-bug.md"
        src_file.write_text("content")
        dest_dir = tmp_path / "new" / "deep" / "dir"

        with patch(
            "langgraph_pipeline.pipeline.nodes.archival.COMPLETED_DIRS",
            {"defect": str(dest_dir)},
        ):
            _move_item_to_completed(str(src_file), "defect")

        assert dest_dir.exists()


# ─── _remove_plan_yaml ────────────────────────────────────────────────────────


class TestRemovePlanYaml:
    def test_deletes_plan_file(self, tmp_path):
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text("meta:\n  name: test\n")
        _remove_plan_yaml(str(plan_file))
        assert not plan_file.exists()

    def test_no_error_when_plan_path_is_none(self):
        _remove_plan_yaml(None)  # Should not raise

    def test_no_error_when_plan_file_missing(self, tmp_path):
        _remove_plan_yaml(str(tmp_path / "nonexistent.yaml"))  # Should not raise


# ─── _build_slack_message ─────────────────────────────────────────────────────


class TestBuildSlackMessage:
    def test_success_message_contains_completed(self):
        msg, level = _build_slack_message("My Bug", "defect", ARCHIVE_OUTCOME_SUCCESS)
        assert "completed" in msg.lower()
        assert level == "success"

    def test_exhausted_message_contains_exhausted(self):
        msg, level = _build_slack_message("My Bug", "defect", ARCHIVE_OUTCOME_EXHAUSTED)
        assert "exhausted" in msg.lower()
        assert level == "error"

    def test_item_name_in_message(self):
        msg, _ = _build_slack_message("My Feature", "feature", ARCHIVE_OUTCOME_SUCCESS)
        assert "My Feature" in msg

    def test_type_label_capitalized_in_message(self):
        msg, _ = _build_slack_message("X", "feature", ARCHIVE_OUTCOME_SUCCESS)
        assert "Feature" in msg


# ─── archive node ─────────────────────────────────────────────────────────────


class TestArchive:
    def test_returns_empty_dict(self, tmp_path):
        state = _make_state(item_path="", plan_path=None)
        with patch(
            "langgraph_pipeline.pipeline.nodes.archival.SlackNotifier"
        ) as mock_notifier_cls:
            mock_notifier_cls.return_value = MagicMock()
            result = archive(state)
        assert result == {}

    def test_moves_item_file(self, tmp_path):
        src_file = tmp_path / "01-bug.md"
        src_file.write_text("# Bug")
        dest_dir = tmp_path / "completed" / "defects"

        state = _make_state(item_path=str(src_file), plan_path=None)

        with patch(
            "langgraph_pipeline.pipeline.nodes.archival.COMPLETED_DIRS",
            {"defect": str(dest_dir), "feature": str(dest_dir), "analysis": str(dest_dir)},
        ), patch("langgraph_pipeline.pipeline.nodes.archival.SlackNotifier") as mock_cls:
            mock_cls.return_value = MagicMock()
            archive(state)

        assert not src_file.exists()
        assert (dest_dir / "01-bug.md").exists()

    def test_removes_plan_yaml(self, tmp_path):
        plan_file = tmp_path / "01-bug.yaml"
        plan_file.write_text("meta:\n  name: test\n")

        state = _make_state(item_path="", plan_path=str(plan_file))

        with patch("langgraph_pipeline.pipeline.nodes.archival.SlackNotifier") as mock_cls:
            mock_cls.return_value = MagicMock()
            archive(state)

        assert not plan_file.exists()

    def test_sends_slack_notification(self):
        state = _make_state(item_path="", plan_path=None)

        with patch(
            "langgraph_pipeline.pipeline.nodes.archival.SlackNotifier"
        ) as mock_notifier_cls:
            mock_instance = MagicMock()
            mock_notifier_cls.return_value = mock_instance
            archive(state)

        mock_instance.send_status.assert_called_once()

    def test_sends_error_level_for_exhausted_defect(self):
        state = _make_defect_fail_state()
        state["item_path"] = ""
        state["plan_path"] = None

        with patch(
            "langgraph_pipeline.pipeline.nodes.archival.SlackNotifier"
        ) as mock_notifier_cls:
            mock_instance = MagicMock()
            mock_notifier_cls.return_value = mock_instance
            archive(state)

        call_kwargs = mock_instance.send_status.call_args
        assert call_kwargs[1]["level"] == "error" or (
            len(call_kwargs[0]) >= 2 and call_kwargs[0][1] == "error"
        )

    def test_sends_success_level_for_passing_defect(self):
        state = _make_state(item_path="", plan_path=None)  # PASS record in history

        with patch(
            "langgraph_pipeline.pipeline.nodes.archival.SlackNotifier"
        ) as mock_notifier_cls:
            mock_instance = MagicMock()
            mock_notifier_cls.return_value = mock_instance
            archive(state)

        call_kwargs = mock_instance.send_status.call_args
        assert call_kwargs[1]["level"] == "success" or (
            len(call_kwargs[0]) >= 2 and call_kwargs[0][1] == "success"
        )

    def test_no_error_when_item_path_empty(self):
        state = _make_state(item_path="", plan_path=None)

        with patch("langgraph_pipeline.pipeline.nodes.archival.SlackNotifier") as mock_cls:
            mock_cls.return_value = MagicMock()
            result = archive(state)  # Should not raise

        assert result == {}

    def test_no_error_when_plan_path_none(self):
        state = _make_state(item_path="", plan_path=None)

        with patch("langgraph_pipeline.pipeline.nodes.archival.SlackNotifier") as mock_cls:
            mock_cls.return_value = MagicMock()
            result = archive(state)  # Should not raise

        assert result == {}


# ─── _strip_trace_id_line ─────────────────────────────────────────────────────


class TestStripTraceIdLine:
    def test_removes_trace_line_from_file(self, tmp_path):
        item_file = tmp_path / "01-bug.md"
        trace_id = "12345678-1234-1234-1234-123456789abc"
        item_file.write_text(f"# Bug\n\nSome content.\n\n## LangSmith Trace: {trace_id}\n")

        _strip_trace_id_line(str(item_file))

        result = item_file.read_text()
        assert "LangSmith Trace" not in result
        assert trace_id not in result
        assert "Some content." in result

    def test_noop_when_no_trace_line_present(self, tmp_path):
        item_file = tmp_path / "01-bug.md"
        original = "# Bug\n\nNo trace line here.\n"
        item_file.write_text(original)

        _strip_trace_id_line(str(item_file))

        assert item_file.read_text() == "# Bug\n\nNo trace line here.\n"

    def test_no_error_when_file_missing(self, tmp_path):
        _strip_trace_id_line(str(tmp_path / "nonexistent.md"))  # Should not raise

    def test_normalizes_trailing_newlines(self, tmp_path):
        item_file = tmp_path / "01-bug.md"
        trace_id = "12345678-1234-1234-1234-123456789abc"
        item_file.write_text(f"# Bug\n\n## LangSmith Trace: {trace_id}\n")

        _strip_trace_id_line(str(item_file))

        result = item_file.read_text()
        assert result.endswith("\n")
        assert not result.endswith("\n\n")


# ─── archive node — trace finalization ────────────────────────────────────────


class TestArchiveTraceFinalization:
    def test_calls_finalize_root_run_with_run_id(self, tmp_path):
        src_file = tmp_path / "01-bug.md"
        src_file.write_text("# Bug\n")
        trace_id = "12345678-1234-1234-1234-123456789abc"
        state = _make_state(
            item_path=str(src_file),
            plan_path=None,
            langsmith_root_run_id=trace_id,
        )
        dest_dir = tmp_path / "completed"

        with patch("langgraph_pipeline.pipeline.nodes.archival.SlackNotifier") as mock_cls, \
             patch("langgraph_pipeline.pipeline.nodes.archival.finalize_root_run") as mock_finalize, \
             patch(
                 "langgraph_pipeline.pipeline.nodes.archival.COMPLETED_DIRS",
                 {"defect": str(dest_dir), "feature": str(dest_dir)},
             ):
            mock_cls.return_value = MagicMock()
            archive(state)

        mock_finalize.assert_called_once_with(
            trace_id,
            {"item_slug": "01-bug", "outcome": ARCHIVE_OUTCOME_SUCCESS},
        )

    def test_calls_finalize_root_run_with_none_when_no_run_id(self, tmp_path):
        state = _make_state(item_path="", plan_path=None)

        with patch("langgraph_pipeline.pipeline.nodes.archival.SlackNotifier") as mock_cls, \
             patch("langgraph_pipeline.pipeline.nodes.archival.finalize_root_run") as mock_finalize:
            mock_cls.return_value = MagicMock()
            archive(state)

        mock_finalize.assert_called_once()
        call_args = mock_finalize.call_args[0]
        assert call_args[0] is None

    def test_strips_trace_id_line_before_move(self, tmp_path):
        trace_id = "12345678-1234-1234-1234-123456789abc"
        src_file = tmp_path / "01-bug.md"
        src_file.write_text(f"# Bug\n\nContent.\n\n## LangSmith Trace: {trace_id}\n")
        dest_dir = tmp_path / "completed" / "defects"

        state = _make_state(
            item_path=str(src_file),
            plan_path=None,
            langsmith_root_run_id=trace_id,
        )

        with patch("langgraph_pipeline.pipeline.nodes.archival.SlackNotifier") as mock_cls, \
             patch("langgraph_pipeline.pipeline.nodes.archival.finalize_root_run"), \
             patch(
                 "langgraph_pipeline.pipeline.nodes.archival.COMPLETED_DIRS",
                 {"defect": str(dest_dir), "feature": str(dest_dir)},
             ):
            mock_cls.return_value = MagicMock()
            archive(state)

        archived_file = dest_dir / "01-bug.md"
        assert archived_file.exists()
        archived_content = archived_file.read_text()
        assert "LangSmith Trace" not in archived_content
        assert "Content." in archived_content
