# tests/langgraph/pipeline/nodes/test_archival.py
# Unit tests for the archive node.
# Design: docs/plans/2026-02-26-04-pipeline-graph-nodes-design.md

"""Tests for langgraph_pipeline.pipeline.nodes.archival."""

import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from langgraph_pipeline.pipeline.nodes.archival import (
    ARCHIVE_OUTCOME_DEADLOCK,
    ARCHIVE_OUTCOME_EXHAUSTED,
    ARCHIVE_OUTCOME_INCOMPLETE,
    ARCHIVE_OUTCOME_SUCCESS,
    ARCHIVE_TERMINAL_STATUSES,
    ARCHIVE_WARNINGS_FILENAME,
    _build_slack_message,
    _determine_outcome,
    _find_non_terminal_tasks,
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
        "plan_path": "tmp/plans/01-bug.yaml",
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


def _write_plan_yaml(path, sections_data) -> None:
    """Write a minimal plan YAML to *path* with the given sections structure."""
    import yaml
    data = {"sections": sections_data}
    Path(path).write_text(yaml.dump(data))


# ─── _find_non_terminal_tasks ─────────────────────────────────────────────────


class TestFindNonTerminalTasks:
    def test_returns_empty_when_plan_path_none(self):
        assert _find_non_terminal_tasks(None) == []

    def test_returns_empty_when_plan_file_missing(self, tmp_path):
        assert _find_non_terminal_tasks(str(tmp_path / "nonexistent.yaml")) == []

    def test_returns_empty_when_all_tasks_terminal(self, tmp_path):
        plan = tmp_path / "plan.yaml"
        _write_plan_yaml(plan, [
            {"id": "1", "name": "S1", "tasks": [
                {"id": "1.1", "name": "Task A", "status": "verified"},
                {"id": "1.2", "name": "Task B", "status": "failed"},
                {"id": "1.3", "name": "Task C", "status": "skipped"},
            ]}
        ])
        assert _find_non_terminal_tasks(str(plan)) == []

    def test_returns_non_terminal_tasks_when_mixed(self, tmp_path):
        plan = tmp_path / "plan.yaml"
        _write_plan_yaml(plan, [
            {"id": "1", "name": "S1", "tasks": [
                {"id": "1.1", "name": "Done Task", "status": "verified"},
                {"id": "1.2", "name": "Pending Task", "status": "pending"},
                {"id": "1.3", "name": "Blocked Task", "status": "blocked"},
            ]}
        ])
        result = _find_non_terminal_tasks(str(plan))
        assert len(result) == 2
        assert ("1.2", "Pending Task", "pending") in result
        assert ("1.3", "Blocked Task", "blocked") in result

    def test_enumerates_tasks_across_all_sections(self, tmp_path):
        plan = tmp_path / "plan.yaml"
        _write_plan_yaml(plan, [
            {"id": "1", "name": "S1", "tasks": [
                {"id": "1.1", "name": "Task A", "status": "verified"},
            ]},
            {"id": "2", "name": "S2", "tasks": [
                {"id": "2.1", "name": "Task B", "status": "pending"},
            ]},
        ])
        result = _find_non_terminal_tasks(str(plan))
        assert result == [("2.1", "Task B", "pending")]

    def test_terminal_statuses_are_exactly_verified_failed_skipped(self):
        assert ARCHIVE_TERMINAL_STATUSES == {"verified", "failed", "skipped"}

    def test_returns_empty_when_sections_key_missing(self, tmp_path):
        plan = tmp_path / "plan.yaml"
        import yaml
        plan.write_text(yaml.dump({"meta": {"name": "test"}}))
        assert _find_non_terminal_tasks(str(plan)) == []


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
        assert _determine_outcome(state, []) == ARCHIVE_OUTCOME_SUCCESS

    def test_analysis_is_always_success(self):
        state = _make_state(
            item_type="analysis",
            verification_history=[],
        )
        assert _determine_outcome(state, []) == ARCHIVE_OUTCOME_SUCCESS

    def test_defect_with_pass_is_success(self):
        state = _make_state(item_type="defect")  # has PASS record
        assert _determine_outcome(state, []) == ARCHIVE_OUTCOME_SUCCESS

    def test_defect_with_fail_is_exhausted(self):
        state = _make_defect_fail_state()
        assert _determine_outcome(state, []) == ARCHIVE_OUTCOME_EXHAUSTED

    def test_defect_with_no_history_is_exhausted(self):
        state = _make_state(item_type="defect", verification_history=[])
        assert _determine_outcome(state, []) == ARCHIVE_OUTCOME_EXHAUSTED

    def test_non_terminal_tasks_override_feature_success(self):
        state = _make_state(item_type="feature", verification_history=[])
        pending = [("1.1", "Task", "pending")]
        assert _determine_outcome(state, pending) == ARCHIVE_OUTCOME_INCOMPLETE

    def test_non_terminal_tasks_override_defect_pass(self):
        state = _make_state(item_type="defect")  # has PASS record
        pending = [("1.2", "Task", "blocked")]
        assert _determine_outcome(state, pending) == ARCHIVE_OUTCOME_INCOMPLETE

    def test_empty_non_terminal_list_does_not_change_outcome(self):
        state = _make_state(item_type="feature", verification_history=[])
        assert _determine_outcome(state, []) == ARCHIVE_OUTCOME_SUCCESS

    def test_none_non_terminal_means_unknown_state_is_incomplete(self):
        state = _make_state(item_type="feature", verification_history=[])
        assert _determine_outcome(state, None) == ARCHIVE_OUTCOME_INCOMPLETE

    def test_executor_deadlock_returns_deadlock_outcome(self):
        state = _make_state(executor_deadlock=True)
        assert _determine_outcome(state) == ARCHIVE_OUTCOME_DEADLOCK

    def test_executor_deadlock_overrides_non_terminal_tasks(self):
        # Deadlock takes priority — it is the most specific failure classification.
        state = _make_state(executor_deadlock=True)
        pending = [("0.4", "Blocked Task", "pending")]
        assert _determine_outcome(state, pending) == ARCHIVE_OUTCOME_DEADLOCK

    def test_executor_deadlock_overrides_incomplete_for_feature(self):
        state = _make_state(item_type="feature", executor_deadlock=True, verification_history=[])
        assert _determine_outcome(state) == ARCHIVE_OUTCOME_DEADLOCK

    def test_no_deadlock_does_not_change_success_outcome(self):
        state = _make_state(item_type="feature", executor_deadlock=False, verification_history=[])
        assert _determine_outcome(state, []) == ARCHIVE_OUTCOME_SUCCESS


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

    def test_incomplete_message_has_warning_level(self):
        pending = [("1.1", "My Task", "pending")]
        _, level = _build_slack_message("Item", "feature", ARCHIVE_OUTCOME_INCOMPLETE, pending)
        assert level == "warning"

    def test_incomplete_message_contains_incomplete(self):
        pending = [("1.1", "My Task", "pending")]
        msg, _ = _build_slack_message("Item", "feature", ARCHIVE_OUTCOME_INCOMPLETE, pending)
        assert "incomplete" in msg.lower()

    def test_incomplete_message_lists_task_id(self):
        pending = [("1.2", "Pending Task", "pending"), ("1.3", "Blocked Task", "blocked")]
        msg, _ = _build_slack_message("Item", "defect", ARCHIVE_OUTCOME_INCOMPLETE, pending)
        assert "1.2" in msg
        assert "1.3" in msg
        assert "pending" in msg
        assert "blocked" in msg

    def test_deadlock_message_has_error_level(self):
        msg, level = _build_slack_message("My Bug", "defect", ARCHIVE_OUTCOME_DEADLOCK)
        assert level == "error"

    def test_deadlock_message_contains_deadlock(self):
        msg, _ = _build_slack_message("My Bug", "defect", ARCHIVE_OUTCOME_DEADLOCK)
        assert "deadlock" in msg.lower()

    def test_deadlock_message_contains_item_name(self):
        msg, _ = _build_slack_message("My Feature", "feature", ARCHIVE_OUTCOME_DEADLOCK)
        assert "My Feature" in msg

    def test_deadlock_message_lists_blocked_task_ids(self):
        details = [
            {"task_id": "0.4", "task_name": "Build UI", "unsatisfied_deps": ["0.3"]},
            {"task_id": "0.5", "task_name": "Run Tests", "unsatisfied_deps": ["0.3", "0.4"]},
        ]
        msg, _ = _build_slack_message("Item", "defect", ARCHIVE_OUTCOME_DEADLOCK, deadlock_details=details)
        assert "0.4" in msg
        assert "0.5" in msg

    def test_deadlock_message_lists_unsatisfied_deps(self):
        details = [{"task_id": "0.4", "task_name": "T", "unsatisfied_deps": ["0.3"]}]
        msg, _ = _build_slack_message("Item", "defect", ARCHIVE_OUTCOME_DEADLOCK, deadlock_details=details)
        assert "0.3" in msg

    def test_deadlock_message_without_details_is_graceful(self):
        msg, level = _build_slack_message("Item", "defect", ARCHIVE_OUTCOME_DEADLOCK)
        assert level == "error"
        assert "deadlock" in msg.lower()


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


# ─── archive node — pending tasks integration ─────────────────────────────────


class TestArchiveWithPendingTasks:
    def _make_plan_with_pending(self, tmp_path) -> str:
        """Write a plan YAML with one verified task and one pending task."""
        plan = tmp_path / "01-bug.yaml"
        _write_plan_yaml(plan, [
            {"id": "1", "name": "Section", "tasks": [
                {"id": "1.1", "name": "Done", "status": "verified"},
                {"id": "1.2", "name": "Pending Task", "status": "pending"},
            ]}
        ])
        return str(plan)

    def test_outcome_is_incomplete_when_pending_tasks_remain(self, tmp_path):
        plan_path = self._make_plan_with_pending(tmp_path)
        state = _make_state(item_path="", plan_path=plan_path)

        with patch("langgraph_pipeline.pipeline.nodes.archival.SlackNotifier") as mock_cls, \
             patch("langgraph_pipeline.pipeline.nodes.archival.WORKER_OUTPUT_DIR", tmp_path), \
             patch("langgraph_pipeline.pipeline.nodes.archival._preserve_plan_yaml"):
            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance
            archive(state)

        call_kwargs = mock_instance.send_status.call_args
        level = call_kwargs[1].get("level") or (
            call_kwargs[0][1] if len(call_kwargs[0]) >= 2 else None
        )
        assert level == "warning"

    def test_slack_message_lists_non_terminal_tasks(self, tmp_path):
        plan_path = self._make_plan_with_pending(tmp_path)
        state = _make_state(item_path="", plan_path=plan_path)

        with patch("langgraph_pipeline.pipeline.nodes.archival.SlackNotifier") as mock_cls, \
             patch("langgraph_pipeline.pipeline.nodes.archival.WORKER_OUTPUT_DIR", tmp_path), \
             patch("langgraph_pipeline.pipeline.nodes.archival._preserve_plan_yaml"):
            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance
            archive(state)

        call_kwargs = mock_instance.send_status.call_args
        message = call_kwargs[0][0]
        assert "1.2" in message
        assert "pending" in message

    def test_archive_warnings_file_written_to_worker_output(self, tmp_path):
        plan_path = self._make_plan_with_pending(tmp_path)
        slug = "01-bug"
        state = _make_state(item_slug=slug, item_path="", plan_path=plan_path)

        with patch("langgraph_pipeline.pipeline.nodes.archival.SlackNotifier") as mock_cls, \
             patch("langgraph_pipeline.pipeline.nodes.archival.WORKER_OUTPUT_DIR", tmp_path), \
             patch("langgraph_pipeline.pipeline.nodes.archival._preserve_plan_yaml"):
            mock_cls.return_value = MagicMock()
            archive(state)

        warnings_file = tmp_path / slug / ARCHIVE_WARNINGS_FILENAME
        assert warnings_file.exists(), "archive-warnings.txt must be written to worker-output"
        content = warnings_file.read_text()
        assert "1.2" in content
        assert "pending" in content

    def test_no_warnings_file_when_all_tasks_terminal(self, tmp_path):
        plan = tmp_path / "01-bug.yaml"
        _write_plan_yaml(plan, [
            {"id": "1", "name": "Section", "tasks": [
                {"id": "1.1", "name": "Done", "status": "verified"},
            ]}
        ])
        slug = "01-bug"
        state = _make_state(item_slug=slug, item_path="", plan_path=str(plan))

        with patch("langgraph_pipeline.pipeline.nodes.archival.SlackNotifier") as mock_cls, \
             patch("langgraph_pipeline.pipeline.nodes.archival.WORKER_OUTPUT_DIR", tmp_path), \
             patch("langgraph_pipeline.pipeline.nodes.archival._preserve_plan_yaml"):
            mock_cls.return_value = MagicMock()
            archive(state)

        warnings_file = tmp_path / slug / ARCHIVE_WARNINGS_FILENAME
        assert not warnings_file.exists(), "archive-warnings.txt must NOT be written when all tasks are terminal"


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
            item_slug="01-bug",
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
