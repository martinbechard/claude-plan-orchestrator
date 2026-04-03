# tests/langgraph/pipeline/nodes/test_plan_creation.py
# Unit tests for the create_plan node.
# Design: docs/plans/2026-02-26-04-pipeline-graph-nodes-design.md

"""Tests for langgraph_pipeline.pipeline.nodes.plan_creation."""

import os
from unittest.mock import MagicMock, patch

import pytest
import yaml

from langgraph_pipeline.pipeline.nodes.plan_creation import (
    DESIGN_DIR,
    PLANNER_ALLOWED_TOOLS,
    PLAN_CREATION_TIMEOUT_SECONDS,
    PLANS_DIR,
    _build_planner_command,
    _plan_exists,
    _run_subprocess,
    create_plan,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_state(**overrides) -> dict:
    """Build a minimal PipelineState dict."""
    base = {
        "item_path": "docs/defect-backlog/01-bug.md",
        "item_slug": "01-bug",
        "item_type": "defect",
        "item_name": "01 Bug",
        "plan_path": None,
        "design_doc_path": None,
        "workspace_path": None,
        "requirements_path": "",
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


def _write_yaml_plan(path) -> None:
    """Write a minimal valid YAML plan to path."""
    plan = {
        "meta": {"name": "Test Plan", "source_item": "docs/defect-backlog/01-bug.md"},
        "sections": [
            {
                "id": "s1",
                "name": "Section",
                "tasks": [{"id": "1.1", "name": "Task", "status": "pending"}],
            }
        ],
    }
    path.write_text(yaml.dump(plan))


# ─── _plan_exists ─────────────────────────────────────────────────────────────


class TestPlanExists:
    def test_returns_false_when_missing(self, tmp_path):
        assert _plan_exists(str(tmp_path / "nonexistent.yaml")) is False

    def test_returns_false_when_empty(self, tmp_path):
        p = tmp_path / "empty.yaml"
        p.write_text("")
        assert _plan_exists(str(p)) is False

    def test_returns_true_when_file_has_content(self, tmp_path):
        p = tmp_path / "plan.yaml"
        p.write_text("meta:\n  name: Test\n")
        assert _plan_exists(str(p)) is True


# ─── _build_planner_command ───────────────────────────────────────────────────


class TestBuildPlannerCommand:
    def test_sandbox_enabled_includes_allowed_tools(self):
        with patch.dict(os.environ, {"ORCHESTRATOR_SANDBOX_ENABLED": "true"}):
            cmd = _build_planner_command("test prompt")
        assert "--allowedTools" in cmd
        for tool in PLANNER_ALLOWED_TOOLS:
            assert tool in cmd
        assert "--permission-mode" in cmd
        assert "acceptEdits" in cmd

    def test_sandbox_disabled_uses_dangerously_skip(self):
        with patch.dict(os.environ, {"ORCHESTRATOR_SANDBOX_ENABLED": "false"}):
            cmd = _build_planner_command("test prompt")
        assert "--dangerously-skip-permissions" in cmd
        assert "--allowedTools" not in cmd

    def test_prompt_appended_with_print_flag(self):
        with patch.dict(os.environ, {"ORCHESTRATOR_SANDBOX_ENABLED": "false"}):
            cmd = _build_planner_command("my prompt")
        assert "--print" in cmd
        assert "my prompt" in cmd

    def test_first_element_is_claude_binary(self):
        with patch.dict(os.environ, {"ORCHESTRATOR_SANDBOX_ENABLED": "false"}):
            cmd = _build_planner_command("p")
        assert cmd[0] == "claude"


# ─── _run_subprocess ──────────────────────────────────────────────────────────


class TestRunSubprocess:
    def test_returns_zero_exit_and_stdout_on_success(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="plan created", stderr=""
            )
            exit_code, stdout, stderr = _run_subprocess(["echo", "ok"])
        assert exit_code == 0
        assert stdout == "plan created"
        assert stderr == ""

    def test_returns_nonzero_on_failure(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="", stderr="error msg"
            )
            exit_code, _stdout, stderr = _run_subprocess(["false"])
        assert exit_code == 1
        assert "error msg" in stderr

    def test_returns_minus_one_on_timeout(self):
        import subprocess as sp

        with patch("subprocess.run", side_effect=sp.TimeoutExpired(cmd="x", timeout=1)):
            exit_code, _stdout, stderr = _run_subprocess(["cmd"])
        assert exit_code == -1
        assert "timed out" in stderr.lower()

    def test_returns_minus_one_on_os_error(self):
        with patch("subprocess.run", side_effect=OSError("no such file")):
            exit_code, _stdout, stderr = _run_subprocess(["nonexistent"])
        assert exit_code == -1
        assert "no such file" in stderr

    def test_removes_claudecode_from_env(self):
        captured_env = {}

        def capture(cmd, **kwargs):
            captured_env.update(kwargs.get("env", {}))
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch.dict(os.environ, {"CLAUDECODE": "1"}):
            with patch("subprocess.run", side_effect=capture):
                _run_subprocess(["cmd"])
        assert "CLAUDECODE" not in captured_env


# ─── create_plan node ─────────────────────────────────────────────────────────


class TestCreatePlan:
    def test_short_circuits_when_plan_path_already_set(self, tmp_path):
        """When plan_path points to an existing file, skip Claude invocation."""
        plan_file = tmp_path / "01-bug.yaml"
        plan_file.write_text("meta:\n  name: Existing\n")

        state = _make_state(plan_path=str(plan_file))
        with patch(
            "langgraph_pipeline.pipeline.nodes.plan_creation._run_subprocess"
        ) as mock_run:
            result = create_plan(state)
        mock_run.assert_not_called()
        assert result == {}

    def test_does_not_short_circuit_when_plan_path_missing_file(self, tmp_path):
        """When plan_path is set but file doesn't exist, proceeds with creation."""
        state = _make_state(plan_path=str(tmp_path / "missing.yaml"))

        with patch(
            "langgraph_pipeline.pipeline.nodes.plan_creation._run_subprocess"
        ) as mock_run:
            mock_run.return_value = (-1, "", "fail")
            result = create_plan(state)
        mock_run.assert_called_once()
        assert result == {}

    def test_returns_empty_on_subprocess_failure(self):
        state = _make_state()
        with patch(
            "langgraph_pipeline.pipeline.nodes.plan_creation._run_subprocess",
            return_value=(1, "", "Claude error"),
        ):
            result = create_plan(state)
        assert result == {}

    def test_returns_empty_when_plan_file_not_created(self, tmp_path, monkeypatch):
        state = _make_state(item_slug="01-bug")
        monkeypatch.setattr(
            "langgraph_pipeline.pipeline.nodes.plan_creation.PLANS_DIR",
            str(tmp_path),
        )
        with patch(
            "langgraph_pipeline.pipeline.nodes.plan_creation._run_subprocess",
            return_value=(0, "done", ""),
        ):
            result = create_plan(state)
        # Plan file wasn't created by the mock, so the node returns empty.
        assert result == {}

    def test_returns_plan_and_design_doc_paths_on_success(self, tmp_path, monkeypatch):
        slug = "01-bug"
        plan_file = tmp_path / f"{slug}.yaml"
        plan_file.write_text("meta:\n  name: Test\n")

        monkeypatch.setattr(
            "langgraph_pipeline.pipeline.nodes.plan_creation.PLANS_DIR",
            str(tmp_path),
        )
        state = _make_state(item_slug=slug)

        with patch(
            "langgraph_pipeline.pipeline.nodes.plan_creation._run_subprocess",
            return_value=(0, "plan created", ""),
        ), patch(
            "langgraph_pipeline.pipeline.nodes.plan_creation._ensure_acceptance_criteria_in_design",
            return_value=True,
        ):
            result = create_plan(state)

        assert result["plan_path"] == str(tmp_path / f"{slug}.yaml")
        assert "design_doc_path" in result
        assert slug in result["design_doc_path"]

    def test_sets_rate_limited_when_rate_limit_detected(self):
        rate_limit_stderr = (
            "You've hit your limit · resets Feb 9 at 6pm (America/Toronto)"
        )
        state = _make_state()
        with patch(
            "langgraph_pipeline.pipeline.nodes.plan_creation._run_subprocess",
            return_value=(1, "", rate_limit_stderr),
        ):
            result = create_plan(state)
        assert result.get("rate_limited") is True

    def test_quota_exhausted_when_rate_limit_has_no_reset_time(self):
        rate_limit_stderr = "You've hit your limit"
        state = _make_state()
        with patch(
            "langgraph_pipeline.pipeline.nodes.plan_creation._run_subprocess",
            return_value=(1, "", rate_limit_stderr),
        ):
            result = create_plan(state)
        assert result.get("quota_exhausted") is True
        assert "rate_limited" not in result

    def test_no_false_positive_when_response_text_contains_limit_keywords(self):
        """Quota detection must not match keywords in Claude's successful response."""
        response_json = '{"result": "The check_rate_limit function matches You\'ve hit your limit"}'
        state = _make_state()
        with patch(
            "langgraph_pipeline.pipeline.nodes.plan_creation._run_subprocess",
            return_value=(0, response_json, ""),
        ), patch(
            "langgraph_pipeline.pipeline.nodes.plan_creation._plan_exists",
            return_value=False,
        ):
            result = create_plan(state)
        assert result.get("quota_exhausted") is not True
        assert result.get("rate_limited") is not True

    def test_design_doc_path_contains_date_and_slug(self, tmp_path, monkeypatch):
        slug = "02-feature"
        plan_file = tmp_path / f"{slug}.yaml"
        plan_file.write_text("meta:\n  name: Feature\n")
        monkeypatch.setattr(
            "langgraph_pipeline.pipeline.nodes.plan_creation.PLANS_DIR",
            str(tmp_path),
        )
        state = _make_state(item_slug=slug, item_type="feature")

        with patch(
            "langgraph_pipeline.pipeline.nodes.plan_creation._run_subprocess",
            return_value=(0, "done", ""),
        ), patch(
            "langgraph_pipeline.pipeline.nodes.plan_creation._ensure_acceptance_criteria_in_design",
            return_value=True,
        ):
            result = create_plan(state)

        design_path = result.get("design_doc_path", "")
        assert slug in design_path
        assert "docs/plans" in design_path


# ─── Freshness skip tests ─────────────────────────────────────────────────────

PLAN_CREATION_MODULE = "langgraph_pipeline.pipeline.nodes.plan_creation"


class TestFreshnessSkip:
    """create_plan skips when workspace design.md and plan.yaml are both fresh."""

    def test_skips_when_both_artifacts_fresh(self, tmp_path, monkeypatch):
        """When is_artifact_fresh returns True for both, Claude is not invoked."""
        slug = "01-fresh-bug"
        plan_file = tmp_path / f"{slug}.yaml"
        plan_file.write_text("meta:\n  name: Fresh\n")
        design_file = tmp_path / f"2026-01-01-{slug}-design.md"
        design_file.write_text("# Design\n")

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        requirements = tmp_path / "requirements.md"
        requirements.write_text("# Requirements\n")

        monkeypatch.setattr(PLAN_CREATION_MODULE + ".PLANS_DIR", str(tmp_path))
        monkeypatch.setattr(PLAN_CREATION_MODULE + ".DESIGN_DIR", str(tmp_path))

        state = _make_state(
            item_slug=slug,
            workspace_path=str(workspace),
            requirements_path=str(requirements),
        )

        with patch(
            PLAN_CREATION_MODULE + ".is_artifact_fresh", return_value=True
        ) as mock_fresh, patch(
            PLAN_CREATION_MODULE + "._run_subprocess"
        ) as mock_run:
            result = create_plan(state)

        mock_run.assert_not_called()
        assert result["plan_path"] == str(tmp_path / f"{slug}.yaml")
        assert slug in result["design_doc_path"]

    def test_reruns_when_design_stale(self, tmp_path, monkeypatch):
        """When design is stale (is_artifact_fresh returns False), Claude runs."""
        slug = "01-stale-bug"
        monkeypatch.setattr(PLAN_CREATION_MODULE + ".PLANS_DIR", str(tmp_path))

        state = _make_state(
            item_slug=slug,
            workspace_path=str(tmp_path / "workspace"),
            requirements_path=str(tmp_path / "requirements.md"),
        )

        with patch(
            PLAN_CREATION_MODULE + ".is_artifact_fresh", return_value=False
        ), patch(
            PLAN_CREATION_MODULE + "._run_subprocess",
            return_value=(1, "", "fail"),
        ) as mock_run:
            result = create_plan(state)

        mock_run.assert_called_once()
        assert result == {}

    def test_reruns_when_plan_file_missing_despite_fresh_workspace(self, tmp_path, monkeypatch):
        """Fresh workspace but plan YAML doesn't exist on disk → must re-run."""
        slug = "01-missing-plan"
        design_file = tmp_path / f"2026-01-01-{slug}-design.md"
        design_file.write_text("# Design\n")

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        requirements = tmp_path / "requirements.md"
        requirements.write_text("# Requirements\n")

        monkeypatch.setattr(PLAN_CREATION_MODULE + ".PLANS_DIR", str(tmp_path))
        monkeypatch.setattr(PLAN_CREATION_MODULE + ".DESIGN_DIR", str(tmp_path))

        state = _make_state(
            item_slug=slug,
            workspace_path=str(workspace),
            requirements_path=str(requirements),
        )

        with patch(
            PLAN_CREATION_MODULE + ".is_artifact_fresh", return_value=True
        ), patch(
            PLAN_CREATION_MODULE + "._run_subprocess",
            return_value=(1, "", "fail"),
        ) as mock_run:
            # Plan file does NOT exist, so freshness skip is bypassed
            result = create_plan(state)

        mock_run.assert_called_once()

    def test_skips_freshness_check_when_no_workspace(self):
        """No freshness check when workspace_path is absent."""
        state = _make_state(requirements_path="some-req.md")
        with patch(
            PLAN_CREATION_MODULE + "._run_subprocess",
            return_value=(1, "", "fail"),
        ) as mock_run, patch(
            PLAN_CREATION_MODULE + ".is_artifact_fresh"
        ) as mock_fresh:
            create_plan(state)

        mock_fresh.assert_not_called()

    def test_skips_freshness_check_when_no_requirements_path(self, tmp_path):
        """No freshness check when requirements_path is absent."""
        state = _make_state(
            workspace_path=str(tmp_path),
            requirements_path="",
        )
        with patch(
            PLAN_CREATION_MODULE + "._run_subprocess",
            return_value=(1, "", "fail"),
        ), patch(
            PLAN_CREATION_MODULE + ".is_artifact_fresh"
        ) as mock_fresh:
            create_plan(state)

        mock_fresh.assert_not_called()

    def test_records_artifact_after_producing_plan(self, tmp_path, monkeypatch):
        """record_artifact is called for both design.md and plan.yaml after successful run."""
        slug = "01-record-test"
        plan_file = tmp_path / f"{slug}.yaml"
        plan_file.write_text("meta:\n  name: Test\n")
        design_file = tmp_path / f"2026-01-01-{slug}-design.md"
        design_file.write_text("# Design\n")

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        requirements = tmp_path / "requirements.md"
        requirements.write_text("# Requirements\n")

        monkeypatch.setattr(PLAN_CREATION_MODULE + ".PLANS_DIR", str(tmp_path))
        monkeypatch.setattr(PLAN_CREATION_MODULE + ".DESIGN_DIR", str(tmp_path))

        state = _make_state(
            item_slug=slug,
            workspace_path=str(workspace),
            requirements_path=str(requirements),
        )

        with patch(
            PLAN_CREATION_MODULE + ".is_artifact_fresh", return_value=False
        ), patch(
            PLAN_CREATION_MODULE + "._run_subprocess",
            return_value=(0, "done", ""),
        ), patch(
            PLAN_CREATION_MODULE + "._ensure_acceptance_criteria_in_design",
            return_value=True,
        ), patch(
            PLAN_CREATION_MODULE + ".record_artifact"
        ) as mock_record:
            create_plan(state)

        # Should record both design.md and plan.yaml
        assert mock_record.call_count == 2
        calls = [call.args[1] for call in mock_record.call_args_list]
        assert "design.md" in calls
        assert "plan.yaml" in calls
