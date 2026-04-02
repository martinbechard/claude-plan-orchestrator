# tests/langgraph/web/routes/test_item_stages.py
# Unit tests for stage data model, build_stages(), and _compute_stage_statuses().
# Design: docs/plans/2026-04-02-74-item-page-step-explorer-design.md

"""Tests for stage data model (D1), status matrix (D2), timestamps (D3/D4),
/dynamic extension (D5), and User Request label (D7).

Covers AC1, AC5, AC6, AC11-AC21, AC24, AC26, AC27.
"""

import time
from pathlib import Path
from typing import Optional
from unittest.mock import patch

import pytest

from langgraph_pipeline.web.routes.item import (
    STAGE_ORDER,
    ArtifactInfo,
    StageInfo,
    _STAGE_CLAIMED,
    _STAGE_COMPLETED,
    _STAGE_DESIGNING,
    _STAGE_EXECUTING,
    _STAGE_ID_TO_ORDER_INDEX,
    _STAGE_PLANNING,
    _STAGE_QUEUED,
    _STAGE_STATUS_DONE,
    _STAGE_STATUS_IN_PROGRESS,
    _STAGE_STATUS_NOT_STARTED,
    _STAGE_STUCK,
    _STAGE_UNKNOWN,
    _STAGE_VALIDATING,
    _compute_stage_statuses,
    _format_timestamp,
    _make_artifact,
    build_stages,
)

# ─── Constants ────────────────────────────────────────────────────────────────

_MODULE = "langgraph_pipeline.web.routes.item"
_TEST_SLUG = "74-step-explorer"
_SAMPLE_EPOCH = 1743580800.0  # 2025-04-02 12:00:00 approx


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _empty_stages(item_type: Optional[str] = "defect") -> list[StageInfo]:
    """Build a minimal list of StageInfo with no artifacts, all not_started."""
    stages: list[StageInfo] = []
    for stage_id, stage_name in STAGE_ORDER:
        if stage_id == "verification" and item_type == "feature":
            continue
        stages.append({
            "id": stage_id,
            "name": stage_name,
            "status": _STAGE_STATUS_NOT_STARTED,
            "artifacts": [],
            "completion_ts": None,
            "completion_epoch": None,
        })
    return stages


def _make_test_artifact(name: str = "test.md", ts: float = _SAMPLE_EPOCH) -> ArtifactInfo:
    """Create a synthetic ArtifactInfo for testing (no filesystem access)."""
    return {
        "name": name,
        "path": f"tmp/{name}",
        "timestamp": ts,
        "timestamp_display": _format_timestamp(ts),
    }


# ─── STAGE_ORDER and _STAGE_ID_TO_ORDER_INDEX (D1) ──────────────────────────


class TestStageOrderConstants:
    """Verify STAGE_ORDER and derived index mapping."""

    def test_stage_order_has_six_entries(self) -> None:
        assert len(STAGE_ORDER) == 6

    def test_stage_order_sequence(self) -> None:
        ids = [sid for sid, _ in STAGE_ORDER]
        assert ids == [
            "intake", "requirements", "planning",
            "execution", "verification", "archive",
        ]

    def test_stage_id_to_order_index_maps_all(self) -> None:
        for i, (sid, _) in enumerate(STAGE_ORDER):
            assert _STAGE_ID_TO_ORDER_INDEX[sid] == i


# ─── _format_timestamp (D3/D4) ──────────────────────────────────────────────


class TestFormatTimestamp:
    """Verify timestamp formatting for artifacts and stages."""

    def test_zero_epoch_returns_empty(self) -> None:
        assert _format_timestamp(0.0) == ""

    def test_valid_epoch_formats_correctly(self) -> None:
        result = _format_timestamp(_SAMPLE_EPOCH)
        # Should be "YYYY-MM-DD HH:MM" format
        assert len(result.split("-")) == 3
        assert ":" in result

    def test_format_is_local_time(self) -> None:
        # Verifies the format pattern, not exact value (timezone-dependent)
        result = _format_timestamp(_SAMPLE_EPOCH)
        parts = result.split(" ")
        assert len(parts) == 2
        assert len(parts[0].split("-")) == 3  # date
        assert len(parts[1].split(":")) == 2  # time HH:MM


# ─── _make_artifact (D4) ─────────────────────────────────────────────────────


class TestMakeArtifact:
    """Verify ArtifactInfo creation from file paths."""

    def test_existing_file_gets_mtime(self, tmp_path: Path) -> None:
        f = tmp_path / "test.md"
        f.write_text("content")
        artifact = _make_artifact("Test", f)
        assert artifact["name"] == "Test"
        assert artifact["path"] == str(f)
        assert artifact["timestamp"] > 0.0
        assert artifact["timestamp_display"] != ""

    def test_missing_file_gets_zero_sentinel(self, tmp_path: Path) -> None:
        missing = tmp_path / "nonexistent.md"
        artifact = _make_artifact("Missing", missing)
        assert artifact["timestamp"] == 0.0
        assert artifact["timestamp_display"] == ""


# ─── _compute_stage_statuses (D2) ───────────────────────────────────────────


class TestComputeStageStatuses:
    """Verify the status computation matrix and done* adjustment."""

    def test_queued_all_not_started(self) -> None:
        stages = _empty_stages()
        _compute_stage_statuses(stages, _STAGE_QUEUED)
        for s in stages:
            assert s["status"] == _STAGE_STATUS_NOT_STARTED

    def test_unknown_all_not_started(self) -> None:
        stages = _empty_stages()
        _compute_stage_statuses(stages, _STAGE_UNKNOWN)
        for s in stages:
            assert s["status"] == _STAGE_STATUS_NOT_STARTED

    def test_claimed_intake_in_progress(self) -> None:
        stages = _empty_stages()
        _compute_stage_statuses(stages, _STAGE_CLAIMED)
        assert stages[0]["status"] == _STAGE_STATUS_IN_PROGRESS  # intake
        for s in stages[1:]:
            assert s["status"] == _STAGE_STATUS_NOT_STARTED

    def test_designing_first_two_done_planning_in_progress(self) -> None:
        stages = _empty_stages()
        # Add artifacts to intake and requirements so done* doesn't downgrade
        stages[0]["artifacts"] = [_make_test_artifact("req.md")]
        stages[1]["artifacts"] = [_make_test_artifact("struct-req.md")]
        _compute_stage_statuses(stages, _STAGE_DESIGNING)
        assert stages[0]["status"] == _STAGE_STATUS_DONE
        assert stages[1]["status"] == _STAGE_STATUS_DONE
        assert stages[2]["status"] == _STAGE_STATUS_IN_PROGRESS  # planning

    def test_executing_first_three_done_execution_in_progress(self) -> None:
        stages = _empty_stages()
        for i in range(3):
            stages[i]["artifacts"] = [_make_test_artifact(f"art-{i}.md")]
        _compute_stage_statuses(stages, _STAGE_EXECUTING)
        assert stages[0]["status"] == _STAGE_STATUS_DONE
        assert stages[1]["status"] == _STAGE_STATUS_DONE
        assert stages[2]["status"] == _STAGE_STATUS_DONE
        assert stages[3]["status"] == _STAGE_STATUS_IN_PROGRESS  # execution

    def test_validating_first_four_done_verification_in_progress(self) -> None:
        stages = _empty_stages()
        for i in range(4):
            stages[i]["artifacts"] = [_make_test_artifact(f"art-{i}.md")]
        _compute_stage_statuses(stages, _STAGE_VALIDATING)
        assert stages[0]["status"] == _STAGE_STATUS_DONE
        assert stages[1]["status"] == _STAGE_STATUS_DONE
        assert stages[2]["status"] == _STAGE_STATUS_DONE
        assert stages[3]["status"] == _STAGE_STATUS_DONE
        assert stages[4]["status"] == _STAGE_STATUS_IN_PROGRESS  # verification
        assert stages[5]["status"] == _STAGE_STATUS_NOT_STARTED  # archive

    def test_completed_all_done(self) -> None:
        stages = _empty_stages()
        _compute_stage_statuses(stages, _STAGE_COMPLETED)
        for s in stages:
            assert s["status"] == _STAGE_STATUS_DONE

    def test_done_star_downgrades_to_in_progress_when_no_artifacts(self) -> None:
        """D2 done* adjustment: done without artifacts -> in_progress."""
        stages = _empty_stages()
        # intake has no artifacts, so done* should downgrade to in_progress
        _compute_stage_statuses(stages, _STAGE_DESIGNING)
        assert stages[0]["status"] == _STAGE_STATUS_IN_PROGRESS  # intake: done* -> in_progress
        assert stages[1]["status"] == _STAGE_STATUS_IN_PROGRESS  # requirements: done* -> in_progress

    def test_done_star_not_applied_when_completed(self) -> None:
        """When pipeline_stage is 'completed', all stages are unconditionally done."""
        stages = _empty_stages()
        # No artifacts at all, but completed means all done
        _compute_stage_statuses(stages, _STAGE_COMPLETED)
        for s in stages:
            assert s["status"] == _STAGE_STATUS_DONE

    def test_feature_omits_verification_and_archive_gets_correct_status(self) -> None:
        """Key bug fix: archive must use canonical STAGE_ORDER index, not filtered position.

        For features, stages = [intake, requirements, planning, execution, archive].
        Archive at filtered index 4 must still map to _BASE_MATRIX column 5 (archive),
        not column 4 (verification).
        """
        stages = _empty_stages(item_type="feature")
        assert len(stages) == 5
        assert stages[4]["id"] == "archive"

        # In validating state: archive should be not_started (column 5),
        # NOT in_progress (column 4 = verification)
        for i in range(4):
            stages[i]["artifacts"] = [_make_test_artifact(f"art-{i}.md")]
        _compute_stage_statuses(stages, _STAGE_VALIDATING)
        assert stages[4]["status"] == _STAGE_STATUS_NOT_STARTED  # archive

    def test_feature_executing_archive_not_started(self) -> None:
        stages = _empty_stages(item_type="feature")
        for i in range(3):
            stages[i]["artifacts"] = [_make_test_artifact(f"art-{i}.md")]
        _compute_stage_statuses(stages, _STAGE_EXECUTING)
        assert stages[3]["status"] == _STAGE_STATUS_IN_PROGRESS  # execution
        assert stages[4]["status"] == _STAGE_STATUS_NOT_STARTED  # archive

    def test_stuck_derives_from_artifact_presence(self) -> None:
        """Unrecognised pipeline_stage: stages with artifacts are done,
        first without is in_progress, rest are not_started."""
        stages = _empty_stages()
        stages[0]["artifacts"] = [_make_test_artifact("req.md")]
        stages[1]["artifacts"] = [_make_test_artifact("struct-req.md")]
        _compute_stage_statuses(stages, _STAGE_STUCK)
        assert stages[0]["status"] == _STAGE_STATUS_DONE
        assert stages[1]["status"] == _STAGE_STATUS_DONE
        assert stages[2]["status"] == _STAGE_STATUS_IN_PROGRESS  # first empty
        assert stages[3]["status"] == _STAGE_STATUS_NOT_STARTED
        assert stages[4]["status"] == _STAGE_STATUS_NOT_STARTED
        assert stages[5]["status"] == _STAGE_STATUS_NOT_STARTED


# ─── build_stages (D1, D3, D5, D7) ──────────────────────────────────────────


class TestBuildStages:
    """Integration tests for build_stages() with filesystem mocked."""

    @patch(f"{_MODULE}._find_original_request_file")
    @patch(f"{_MODULE}._find_structured_requirements_file")
    @patch(f"{_MODULE}._find_design_doc")
    @patch(f"{_MODULE}._find_plan_yaml")
    @patch(f"{_MODULE}.ws_path_fn")
    @patch(f"{_MODULE}.WORKER_OUTPUT_DIR", new_callable=lambda: type("P", (), {"__truediv__": lambda s, o: Path("/nonexistent") / o})())
    def test_defect_returns_six_stages_in_order(
        self, _wo, mock_ws, mock_plan, mock_design, mock_req, mock_orig, tmp_path,
    ) -> None:
        mock_orig.return_value = None
        mock_req.return_value = None
        mock_design.return_value = None
        mock_plan.return_value = None
        mock_ws.return_value = tmp_path / "workspace"
        stages = build_stages(_TEST_SLUG, "defect", _STAGE_QUEUED)
        assert len(stages) == 6
        assert [s["id"] for s in stages] == [
            "intake", "requirements", "planning",
            "execution", "verification", "archive",
        ]

    @patch(f"{_MODULE}._find_original_request_file")
    @patch(f"{_MODULE}._find_structured_requirements_file")
    @patch(f"{_MODULE}._find_design_doc")
    @patch(f"{_MODULE}._find_plan_yaml")
    @patch(f"{_MODULE}.ws_path_fn")
    @patch(f"{_MODULE}.WORKER_OUTPUT_DIR", new_callable=lambda: type("P", (), {"__truediv__": lambda s, o: Path("/nonexistent") / o})())
    def test_feature_returns_five_stages_no_verification(
        self, _wo, mock_ws, mock_plan, mock_design, mock_req, mock_orig, tmp_path,
    ) -> None:
        """AC15: Verification stage omitted for feature items."""
        mock_orig.return_value = None
        mock_req.return_value = None
        mock_design.return_value = None
        mock_plan.return_value = None
        mock_ws.return_value = tmp_path / "workspace"
        stages = build_stages(_TEST_SLUG, "feature", _STAGE_QUEUED)
        assert len(stages) == 5
        assert "verification" not in [s["id"] for s in stages]

    @patch(f"{_MODULE}._find_original_request_file")
    @patch(f"{_MODULE}._find_structured_requirements_file")
    @patch(f"{_MODULE}._find_design_doc")
    @patch(f"{_MODULE}._find_plan_yaml")
    @patch(f"{_MODULE}.ws_path_fn")
    @patch(f"{_MODULE}.WORKER_OUTPUT_DIR", new_callable=lambda: type("P", (), {"__truediv__": lambda s, o: Path("/nonexistent") / o})())
    def test_user_request_label_replaces_raw_input(
        self, _wo, mock_ws, mock_plan, mock_design, mock_req, mock_orig, tmp_path,
    ) -> None:
        """AC26/AC27: Label is 'User Request', underlying path unchanged."""
        req_file = tmp_path / "request.md"
        req_file.write_text("original request")
        mock_orig.return_value = req_file
        mock_req.return_value = None
        mock_design.return_value = None
        mock_plan.return_value = None
        mock_ws.return_value = tmp_path / "workspace"
        stages = build_stages(_TEST_SLUG, "defect", _STAGE_CLAIMED)
        intake = stages[0]
        assert intake["id"] == "intake"
        assert any(a["name"] == "User Request" for a in intake["artifacts"])
        # Underlying path still points to the original file
        user_req = [a for a in intake["artifacts"] if a["name"] == "User Request"][0]
        assert user_req["path"] == str(req_file)

    @patch(f"{_MODULE}._find_original_request_file")
    @patch(f"{_MODULE}._find_structured_requirements_file")
    @patch(f"{_MODULE}._find_design_doc")
    @patch(f"{_MODULE}._find_plan_yaml")
    @patch(f"{_MODULE}.ws_path_fn")
    @patch(f"{_MODULE}.WORKER_OUTPUT_DIR", new_callable=lambda: type("P", (), {"__truediv__": lambda s, o: Path("/nonexistent") / o})())
    def test_done_stage_gets_completion_timestamp(
        self, _wo, mock_ws, mock_plan, mock_design, mock_req, mock_orig, tmp_path,
    ) -> None:
        """AC5/AC19: Completed stage displays timestamp from latest artifact mtime."""
        req_file = tmp_path / "request.md"
        req_file.write_text("content")
        mock_orig.return_value = req_file
        mock_req.return_value = None
        mock_design.return_value = None
        mock_plan.return_value = None
        mock_ws.return_value = tmp_path / "workspace"
        # Intake stage will have an artifact and be marked done when designing
        stages = build_stages(_TEST_SLUG, "defect", _STAGE_DESIGNING)
        intake = stages[0]
        assert intake["status"] == _STAGE_STATUS_DONE
        assert intake["completion_ts"] is not None
        assert intake["completion_epoch"] is not None
        assert intake["completion_epoch"] > 0.0

    @patch(f"{_MODULE}._find_original_request_file")
    @patch(f"{_MODULE}._find_structured_requirements_file")
    @patch(f"{_MODULE}._find_design_doc")
    @patch(f"{_MODULE}._find_plan_yaml")
    @patch(f"{_MODULE}.ws_path_fn")
    @patch(f"{_MODULE}.WORKER_OUTPUT_DIR", new_callable=lambda: type("P", (), {"__truediv__": lambda s, o: Path("/nonexistent") / o})())
    def test_not_started_stage_has_no_timestamp(
        self, _wo, mock_ws, mock_plan, mock_design, mock_req, mock_orig, tmp_path,
    ) -> None:
        """Stages that are not done have no completion timestamp."""
        mock_orig.return_value = None
        mock_req.return_value = None
        mock_design.return_value = None
        mock_plan.return_value = None
        mock_ws.return_value = tmp_path / "workspace"
        stages = build_stages(_TEST_SLUG, "defect", _STAGE_QUEUED)
        for s in stages:
            assert s["completion_ts"] is None
            assert s["completion_epoch"] is None

    @patch(f"{_MODULE}._find_original_request_file")
    @patch(f"{_MODULE}._find_structured_requirements_file")
    @patch(f"{_MODULE}._find_design_doc")
    @patch(f"{_MODULE}._find_plan_yaml")
    @patch(f"{_MODULE}.ws_path_fn")
    @patch(f"{_MODULE}.WORKER_OUTPUT_DIR", new_callable=lambda: type("P", (), {"__truediv__": lambda s, o: Path("/nonexistent") / o})())
    def test_intake_discovers_clause_register_and_five_whys(
        self, _wo, mock_ws, mock_plan, mock_design, mock_req, mock_orig, tmp_path,
    ) -> None:
        """AC11: Intake stage contains user request, clause register, 5 whys."""
        ws = tmp_path / "workspace"
        ws.mkdir()
        (ws / "clauses.md").write_text("clauses")
        (ws / "five-whys.md").write_text("five whys")
        req_file = tmp_path / "request.md"
        req_file.write_text("request")
        mock_orig.return_value = req_file
        mock_req.return_value = None
        mock_design.return_value = None
        mock_plan.return_value = None
        mock_ws.return_value = ws
        stages = build_stages(_TEST_SLUG, "defect", _STAGE_CLAIMED)
        intake = stages[0]
        names = [a["name"] for a in intake["artifacts"]]
        assert "User Request" in names
        assert "Clause Register" in names
        assert "5 Whys Analysis" in names

    @patch(f"{_MODULE}._find_original_request_file")
    @patch(f"{_MODULE}._find_structured_requirements_file")
    @patch(f"{_MODULE}._find_design_doc")
    @patch(f"{_MODULE}._find_plan_yaml")
    @patch(f"{_MODULE}.ws_path_fn")
    @patch(f"{_MODULE}.WORKER_OUTPUT_DIR", new_callable=lambda: type("P", (), {"__truediv__": lambda s, o: Path("/nonexistent") / o})())
    def test_planning_discovers_design_and_yaml(
        self, _wo, mock_ws, mock_plan, mock_design, mock_req, mock_orig, tmp_path,
    ) -> None:
        """AC13: Planning stage contains design document and YAML plan."""
        design_file = tmp_path / "design.md"
        design_file.write_text("design")
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text("plan")
        mock_orig.return_value = None
        mock_req.return_value = None
        mock_design.return_value = design_file
        mock_plan.return_value = plan_file
        mock_ws.return_value = tmp_path / "workspace"
        stages = build_stages(_TEST_SLUG, "defect", _STAGE_PLANNING)
        planning = [s for s in stages if s["id"] == "planning"][0]
        names = [a["name"] for a in planning["artifacts"]]
        assert "Design Document" in names
        assert "YAML Plan" in names

    @patch(f"{_MODULE}._find_original_request_file")
    @patch(f"{_MODULE}._find_structured_requirements_file")
    @patch(f"{_MODULE}._find_design_doc")
    @patch(f"{_MODULE}._find_plan_yaml")
    @patch(f"{_MODULE}.ws_path_fn")
    @patch(f"{_MODULE}.WORKER_OUTPUT_DIR", new_callable=lambda: type("P", (), {"__truediv__": lambda s, o: Path("/nonexistent") / o})())
    def test_artifact_has_file_timestamp(
        self, _wo, mock_ws, mock_plan, mock_design, mock_req, mock_orig, tmp_path,
    ) -> None:
        """AC6/AC21: Each artifact displays its file mtime timestamp."""
        req_file = tmp_path / "request.md"
        req_file.write_text("content")
        mock_orig.return_value = req_file
        mock_req.return_value = None
        mock_design.return_value = None
        mock_plan.return_value = None
        mock_ws.return_value = tmp_path / "workspace"
        stages = build_stages(_TEST_SLUG, "defect", _STAGE_CLAIMED)
        intake = stages[0]
        art = intake["artifacts"][0]
        assert art["timestamp"] > 0.0
        assert art["timestamp_display"] != ""


# ─── /dynamic stage_summaries (D5) ──────────────────────────────────────────


class TestDynamicStageSummaries:
    """Verify that build_stages output supports the /dynamic stage_summaries schema."""

    @patch(f"{_MODULE}._find_original_request_file")
    @patch(f"{_MODULE}._find_structured_requirements_file")
    @patch(f"{_MODULE}._find_design_doc")
    @patch(f"{_MODULE}._find_plan_yaml")
    @patch(f"{_MODULE}.ws_path_fn")
    @patch(f"{_MODULE}.WORKER_OUTPUT_DIR", new_callable=lambda: type("P", (), {"__truediv__": lambda s, o: Path("/nonexistent") / o})())
    def test_stage_summaries_schema(
        self, _wo, mock_ws, mock_plan, mock_design, mock_req, mock_orig, tmp_path,
    ) -> None:
        """AC24: /dynamic stages array has id, status, completion_ts, completion_epoch, artifact_count."""
        mock_orig.return_value = None
        mock_req.return_value = None
        mock_design.return_value = None
        mock_plan.return_value = None
        mock_ws.return_value = tmp_path / "workspace"
        stages = build_stages(_TEST_SLUG, "defect", _STAGE_QUEUED)
        summaries = [
            {
                "id": s["id"],
                "status": s["status"],
                "completion_ts": s["completion_ts"],
                "completion_epoch": s["completion_epoch"],
                "artifact_count": len(s["artifacts"]),
            }
            for s in stages
        ]
        assert len(summaries) == 6
        for sm in summaries:
            assert "id" in sm
            assert sm["status"] in {
                _STAGE_STATUS_NOT_STARTED,
                _STAGE_STATUS_IN_PROGRESS,
                _STAGE_STATUS_DONE,
            }
            assert "completion_ts" in sm
            assert "completion_epoch" in sm
            assert "artifact_count" in sm
            assert isinstance(sm["artifact_count"], int)
