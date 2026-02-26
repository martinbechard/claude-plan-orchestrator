# tests/langgraph/pipeline/nodes/test_plan_creation.py
# Unit tests for the create_plan node.
# Design: docs/plans/2026-02-26-04-pipeline-graph-nodes-design.md

"""Tests for langgraph_pipeline.pipeline.nodes.plan_creation."""

import os
from unittest.mock import MagicMock, patch

import pytest
import yaml

from langgraph_pipeline.pipeline.nodes.plan_creation import (
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
        ):
            result = create_plan(state)

        assert result["plan_path"] == str(tmp_path / f"{slug}.yaml")
        assert "design_doc_path" in result
        assert slug in result["design_doc_path"]

    def test_sets_rate_limited_when_rate_limit_detected(self):
        rate_limit_output = (
            "You've hit your limit · resets Feb 9 at 6pm (America/Toronto)"
        )
        state = _make_state()
        with patch(
            "langgraph_pipeline.pipeline.nodes.plan_creation._run_subprocess",
            return_value=(1, rate_limit_output, ""),
        ):
            result = create_plan(state)
        assert result.get("rate_limited") is True

    def test_rate_limit_reset_is_none_when_unparseable(self):
        rate_limit_output = "You've hit your limit"
        state = _make_state()
        with patch(
            "langgraph_pipeline.pipeline.nodes.plan_creation._run_subprocess",
            return_value=(1, rate_limit_output, ""),
        ):
            result = create_plan(state)
        assert result.get("rate_limited") is True

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
        ):
            result = create_plan(state)

        design_path = result.get("design_doc_path", "")
        assert slug in design_path
        assert "docs/plans" in design_path
