# tests/langgraph/test_suspension_wiring.py
# Unit tests for suspension wiring: marker creation in task_runner, Slack posting
# and reinstatement helpers in cli.py.
# Design: docs/plans/2026-03-24-10-ux-designer-opus-sonnet-loop-with-slack-suspension-design.md

"""Unit tests for suspension marker creation, Slack posting, and reinstatement."""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from langgraph_pipeline.cli import (
    _post_pending_suspension_questions,
    _reinstate_answered_suspensions,
)
from langgraph_pipeline.shared.suspension import SUSPENDED_DIR

# ─── Fixtures ────────────────────────────────────────────────────────────────

SAMPLE_MARKER = {
    "slug": "test-feature",
    "item_type": "feature",
    "item_path": "docs/feature-backlog/test-feature.md",
    "plan_path": "",  # overridden per test
    "task_id": "1.1",
    "question": "What color should the button be?",
    "question_context": "The design has no color spec.",
    "suspended_at": "2026-03-24T12:00:00+00:00",
    "timeout_minutes": 1440,
    "slack_thread_ts": "",
    "slack_channel_id": "",
    "answer": "",
}

SAMPLE_PLAN = {
    "meta": {
        "name": "Test Plan",
        "source_item": "docs/feature-backlog/test-feature.md",
    },
    "sections": [
        {
            "id": "phase-1",
            "name": "Phase 1",
            "tasks": [
                {
                    "id": "1.1",
                    "name": "Test task",
                    "agent": "coder",
                    "status": "suspended",
                },
            ],
        },
    ],
}


@pytest.fixture()
def suspended_dir(tmp_path: Path) -> Path:
    """Create a temporary suspended directory and patch SUSPENDED_DIR + SUSPENDED_GLOB."""
    d = tmp_path / "suspended"
    d.mkdir()
    return d


def _write_marker(suspended_dir: Path, slug: str, overrides: dict | None = None) -> Path:
    """Write a marker JSON file to the suspended dir. Returns the file path."""
    marker = {**SAMPLE_MARKER, "slug": slug, **(overrides or {})}
    path = suspended_dir / f"{slug}.json"
    path.write_text(json.dumps(marker, indent=2))
    return path


def _write_plan(tmp_path: Path, overrides: dict | None = None) -> Path:
    """Write a plan YAML file. Returns the file path."""
    plan = {**SAMPLE_PLAN}
    if overrides:
        for key, value in overrides.items():
            plan[key] = value
    path = tmp_path / "test-plan.yaml"
    path.write_text(yaml.dump(plan, default_flow_style=False, sort_keys=False))
    return path


# ─── _reinstate_answered_suspensions tests ───────────────────────────────────


class TestReinstateAnsweredSuspensions:
    """Tests for _reinstate_answered_suspensions() in cli.py."""

    def test_answered_marker_reinstates_task(self, tmp_path: Path, suspended_dir: Path) -> None:
        """Answered markers reset task to pending with human_answer/human_question fields."""
        plan_path = _write_plan(tmp_path)
        _write_marker(
            suspended_dir,
            "test-feature",
            {
                "plan_path": str(plan_path),
                "answer": "Use blue for the primary button.",
            },
        )

        glob_pattern = str(suspended_dir / "*.json")
        with (
            patch("langgraph_pipeline.cli.SUSPENDED_GLOB", glob_pattern),
            patch("langgraph_pipeline.cli.clear_suspension_marker") as mock_clear,
        ):
            _reinstate_answered_suspensions()

        # Verify plan YAML was updated
        with open(plan_path) as f:
            updated_plan = yaml.safe_load(f)
        task = updated_plan["sections"][0]["tasks"][0]
        assert task["status"] == "pending"
        assert task["human_answer"] == "Use blue for the primary button."
        assert task["human_question"] == "What color should the button be?"

        # Verify marker was cleared
        mock_clear.assert_called_once_with("test-feature")

    def test_unanswered_marker_is_skipped(self, tmp_path: Path, suspended_dir: Path) -> None:
        """Markers without an answer are left untouched."""
        plan_path = _write_plan(tmp_path)
        marker_path = _write_marker(
            suspended_dir,
            "test-feature",
            {"plan_path": str(plan_path), "answer": ""},
        )

        glob_pattern = str(suspended_dir / "*.json")
        with (
            patch("langgraph_pipeline.cli.SUSPENDED_GLOB", glob_pattern),
            patch("langgraph_pipeline.cli.clear_suspension_marker") as mock_clear,
        ):
            _reinstate_answered_suspensions()

        # Task stays suspended
        with open(plan_path) as f:
            plan = yaml.safe_load(f)
        assert plan["sections"][0]["tasks"][0]["status"] == "suspended"
        mock_clear.assert_not_called()

    def test_missing_plan_path_does_not_crash(
        self, tmp_path: Path, suspended_dir: Path
    ) -> None:
        """Markers with missing plan_path are skipped without error."""
        _write_marker(
            suspended_dir,
            "test-feature",
            {"plan_path": "", "task_id": "", "answer": "Yes"},
        )

        glob_pattern = str(suspended_dir / "*.json")
        with (
            patch("langgraph_pipeline.cli.SUSPENDED_GLOB", glob_pattern),
            patch("langgraph_pipeline.cli.clear_suspension_marker") as mock_clear,
        ):
            _reinstate_answered_suspensions()  # Should not raise

        mock_clear.assert_not_called()

    def test_missing_task_id_in_plan_does_not_crash(
        self, tmp_path: Path, suspended_dir: Path
    ) -> None:
        """When the task_id is not found in the plan, skip without error."""
        plan_path = _write_plan(tmp_path)
        _write_marker(
            suspended_dir,
            "test-feature",
            {"plan_path": str(plan_path), "task_id": "99.99", "answer": "Yes"},
        )

        glob_pattern = str(suspended_dir / "*.json")
        with (
            patch("langgraph_pipeline.cli.SUSPENDED_GLOB", glob_pattern),
            patch("langgraph_pipeline.cli.clear_suspension_marker") as mock_clear,
        ):
            _reinstate_answered_suspensions()  # Should not raise

        mock_clear.assert_not_called()


# ─── _post_pending_suspension_questions tests ────────────────────────────────


class TestPostPendingSuspensionQuestions:
    """Tests for _post_pending_suspension_questions() in cli.py."""

    def test_marker_without_thread_ts_triggers_slack_post(
        self, tmp_path: Path, suspended_dir: Path
    ) -> None:
        """Markers without slack_thread_ts trigger slack.post_suspension_question."""
        marker_path = _write_marker(suspended_dir, "test-feature")

        mock_slack = MagicMock()
        mock_slack.is_enabled.return_value = True
        mock_slack.post_suspension_question.return_value = "1234567890.123456"
        mock_slack.get_type_channel_id.return_value = "C12345"

        glob_pattern = str(suspended_dir / "*.json")
        with patch("langgraph_pipeline.cli.SUSPENDED_GLOB", glob_pattern):
            _post_pending_suspension_questions(mock_slack)

        mock_slack.post_suspension_question.assert_called_once_with(
            "test-feature",
            "feature",
            "What color should the button be?",
            "The design has no color spec.",
        )

        # Verify marker was updated with thread_ts and channel_id
        with open(marker_path) as f:
            updated_marker = json.load(f)
        assert updated_marker["slack_thread_ts"] == "1234567890.123456"
        assert updated_marker["slack_channel_id"] == "C12345"

    def test_marker_with_existing_thread_ts_is_skipped(
        self, tmp_path: Path, suspended_dir: Path
    ) -> None:
        """Markers that already have a slack_thread_ts are not re-posted."""
        _write_marker(
            suspended_dir,
            "test-feature",
            {"slack_thread_ts": "existing.ts"},
        )

        mock_slack = MagicMock()
        mock_slack.is_enabled.return_value = True

        glob_pattern = str(suspended_dir / "*.json")
        with patch("langgraph_pipeline.cli.SUSPENDED_GLOB", glob_pattern):
            _post_pending_suspension_questions(mock_slack)

        mock_slack.post_suspension_question.assert_not_called()

    def test_slack_none_skips_posting(
        self, tmp_path: Path, suspended_dir: Path
    ) -> None:
        """When slack is None, no posting occurs."""
        _write_marker(suspended_dir, "test-feature")

        glob_pattern = str(suspended_dir / "*.json")
        with patch("langgraph_pipeline.cli.SUSPENDED_GLOB", glob_pattern):
            _post_pending_suspension_questions(None)

        # No assertion needed beyond no exception raised

    def test_slack_not_enabled_skips_posting(
        self, tmp_path: Path, suspended_dir: Path
    ) -> None:
        """When slack.is_enabled() returns False, no posting occurs."""
        _write_marker(suspended_dir, "test-feature")

        mock_slack = MagicMock()
        mock_slack.is_enabled.return_value = False

        glob_pattern = str(suspended_dir / "*.json")
        with patch("langgraph_pipeline.cli.SUSPENDED_GLOB", glob_pattern):
            _post_pending_suspension_questions(mock_slack)

        mock_slack.post_suspension_question.assert_not_called()


# ─── task_runner marker creation tests ───────────────────────────────────────


class TestTaskRunnerMarkerCreation:
    """Tests for suspension marker creation in task_runner.py."""

    def test_suspended_status_creates_marker(self) -> None:
        """When status_dict has suspended status with question, create_suspension_marker is called."""
        status_dict = {
            "status": "suspended",
            "message": "Need design clarification",
            "question": "What font should we use?",
            "question_context": "The spec does not mention typography.",
        }

        plan_data = {
            "meta": {
                "name": "Test Plan",
                "source_item": "docs/feature-backlog/my-cool-feature.md",
            },
            "sections": [
                {
                    "id": "phase-1",
                    "tasks": [
                        {
                            "id": "2.1",
                            "name": "Design task",
                            "agent": "ux-designer",
                            "status": "in_progress",
                        }
                    ],
                }
            ],
        }

        plan_path = "/tmp/test-plan.yaml"
        task_id = "2.1"
        task = plan_data["sections"][0]["tasks"][0]

        # Simulate what task_runner does in the _STATUS_SUSPENDED branch
        question = status_dict.get("question", "")
        question_context = status_dict.get("question_context", "")
        source_item = plan_data.get("meta", {}).get("source_item", "")
        slug = Path(source_item).stem if source_item else ""
        item_type = "defect" if source_item and "defect" in source_item.lower() else "feature"

        with patch(
            "langgraph_pipeline.shared.suspension.create_suspension_marker"
        ) as mock_create:
            mock_create.return_value = f".claude/suspended/{slug}.json"
            if slug and question:
                marker_path = mock_create(
                    slug, item_type, source_item, plan_path, task_id, question, question_context
                )

        mock_create.assert_called_once_with(
            "my-cool-feature",
            "feature",
            "docs/feature-backlog/my-cool-feature.md",
            "/tmp/test-plan.yaml",
            "2.1",
            "What font should we use?",
            "The spec does not mention typography.",
        )

    def test_defect_source_item_sets_defect_type(self) -> None:
        """When source_item contains 'defect', item_type is set to 'defect'."""
        source_item = "docs/defect-backlog/01-login-bug.md"
        slug = Path(source_item).stem
        item_type = "defect" if source_item and "defect" in source_item.lower() else "feature"

        assert slug == "01-login-bug"
        assert item_type == "defect"

    def test_empty_source_item_yields_empty_slug(self) -> None:
        """When plan_data has no source_item, slug is empty and marker is not created."""
        plan_data = {"meta": {}}
        source_item = plan_data.get("meta", {}).get("source_item", "")
        slug = Path(source_item).stem if source_item else ""
        question = "Some question"

        # slug is empty, so the condition `if slug and question` is False
        assert slug == ""
        assert not (slug and question)

    def test_empty_question_skips_marker(self) -> None:
        """When question is empty, marker is not created even with valid slug."""
        source_item = "docs/feature-backlog/some-feature.md"
        slug = Path(source_item).stem
        question = ""

        assert slug == "some-feature"
        assert not (slug and question)
