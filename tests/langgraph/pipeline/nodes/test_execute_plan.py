# tests/langgraph/pipeline/nodes/test_execute_plan.py
# Unit tests for the execute_plan node.
# Design: docs/plans/2026-02-26-04-pipeline-graph-nodes-design.md

"""Tests for langgraph_pipeline.pipeline.nodes.execute_plan."""

import importlib
import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

# Import the module object directly to avoid name collision with the exported
# `execute_plan` function that shadows the module in the `nodes` package __init__.
execute_plan_mod = importlib.import_module(
    "langgraph_pipeline.pipeline.nodes.execute_plan"
)

from langgraph_pipeline.pipeline.nodes.execute_plan import (
    MAX_PLAN_NAME_LENGTH,
    PLAN_ORCHESTRATOR_SCRIPT,
    _read_plan_name,
    _read_usage_report,
    _spawn_orchestrator,
    _usage_report_path,
    execute_plan,
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


def _write_plan(path, name: str = "Test Plan") -> None:
    """Write a minimal YAML plan file."""
    plan = {
        "meta": {"name": name, "source_item": "docs/defect-backlog/01-bug.md"},
        "sections": [],
    }
    path.write_text(yaml.dump(plan))


def _write_usage_report(path: Path, cost: float, input_tok: int, output_tok: int) -> None:
    """Write a minimal usage report JSON."""
    report = {
        "plan_name": "Test Plan",
        "total": {
            "cost_usd": cost,
            "input_tokens": input_tok,
            "output_tokens": output_tok,
            "cache_read_tokens": 0,
            "cache_creation_tokens": 0,
        },
        "sections": [],
        "tasks": [],
    }
    path.write_text(json.dumps(report))


# ─── _read_plan_name ──────────────────────────────────────────────────────────


class TestReadPlanName:
    def test_returns_plan_name_from_meta(self, tmp_path):
        plan_file = tmp_path / "plan.yaml"
        _write_plan(plan_file, name="My Feature Plan")
        assert _read_plan_name(str(plan_file)) == "My Feature Plan"

    def test_returns_unknown_when_file_missing(self, tmp_path):
        assert _read_plan_name(str(tmp_path / "nonexistent.yaml")) == "unknown"

    def test_returns_unknown_when_meta_missing(self, tmp_path):
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text("sections: []\n")
        assert _read_plan_name(str(plan_file)) == "unknown"

    def test_returns_unknown_when_corrupt_yaml(self, tmp_path):
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(": : invalid yaml\n")
        assert _read_plan_name(str(plan_file)) == "unknown"


# ─── _usage_report_path ───────────────────────────────────────────────────────


class TestUsageReportPath:
    def test_report_filename_derived_from_plan_name(self, tmp_path):
        plan_file = tmp_path / "plan.yaml"
        _write_plan(plan_file, name="My Test Plan")
        report_path = _usage_report_path(str(plan_file))
        assert "my-test-plan-usage-report.json" in str(report_path)

    def test_plan_name_truncated_to_max_length(self, tmp_path):
        long_name = "A" * (MAX_PLAN_NAME_LENGTH + 20)
        plan_file = tmp_path / "plan.yaml"
        _write_plan(plan_file, name=long_name)
        report_path = _usage_report_path(str(plan_file))
        # Filename part before "-usage-report.json" should not exceed max length.
        filename = report_path.name
        prefix = filename.replace("-usage-report.json", "")
        assert len(prefix) <= MAX_PLAN_NAME_LENGTH

    def test_spaces_replaced_with_hyphens(self, tmp_path):
        plan_file = tmp_path / "plan.yaml"
        _write_plan(plan_file, name="Feature With Spaces")
        report_path = _usage_report_path(str(plan_file))
        assert " " not in str(report_path)


# ─── _read_usage_report ───────────────────────────────────────────────────────


class TestReadUsageReport:
    def test_returns_zeros_when_file_missing(self, tmp_path):
        usage = _read_usage_report(tmp_path / "nonexistent.json")
        assert usage == {"cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0}

    def test_parses_cost_and_tokens(self, tmp_path):
        report_file = tmp_path / "report.json"
        _write_usage_report(report_file, cost=1.23, input_tok=5000, output_tok=2000)
        usage = _read_usage_report(report_file)
        assert usage["cost_usd"] == pytest.approx(1.23)
        assert usage["input_tokens"] == 5000
        assert usage["output_tokens"] == 2000

    def test_returns_zeros_on_corrupt_json(self, tmp_path):
        report_file = tmp_path / "bad.json"
        report_file.write_text("not-json")
        usage = _read_usage_report(report_file)
        assert usage == {"cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0}

    def test_returns_zeros_when_total_key_missing(self, tmp_path):
        report_file = tmp_path / "partial.json"
        report_file.write_text(json.dumps({"plan_name": "X"}))
        usage = _read_usage_report(report_file)
        assert usage == {"cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0}


# ─── _spawn_orchestrator ──────────────────────────────────────────────────────


class TestSpawnOrchestrator:
    def test_returns_exit_code_zero_on_success(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="Tasks completed", stderr=""
            )
            exit_code, stdout, stderr = _spawn_orchestrator(".claude/plans/plan.yaml")
        assert exit_code == 0
        assert stdout == "Tasks completed"

    def test_returns_nonzero_on_orchestrator_failure(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="", stderr="orchestrator error"
            )
            exit_code, _stdout, stderr = _spawn_orchestrator(".claude/plans/plan.yaml")
        assert exit_code == 1
        assert "orchestrator error" in stderr

    def test_includes_plan_flag_in_command(self):
        captured_cmd = []

        def capture(cmd, **kwargs):
            captured_cmd.extend(cmd)
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch("subprocess.run", side_effect=capture):
            _spawn_orchestrator(".claude/plans/my-plan.yaml")

        assert "--plan" in captured_cmd
        assert ".claude/plans/my-plan.yaml" in captured_cmd
        assert PLAN_ORCHESTRATOR_SCRIPT in captured_cmd

    def test_removes_claudecode_from_env(self):
        captured_env = {}

        def capture(cmd, **kwargs):
            captured_env.update(kwargs.get("env", {}))
            return MagicMock(returncode=0, stdout="", stderr="")

        with patch.dict(os.environ, {"CLAUDECODE": "1"}):
            with patch("subprocess.run", side_effect=capture):
                _spawn_orchestrator(".claude/plans/plan.yaml")

        assert "CLAUDECODE" not in captured_env

    def test_returns_minus_one_on_os_error(self):
        with patch("subprocess.run", side_effect=OSError("no such file")):
            exit_code, _stdout, stderr = _spawn_orchestrator(".claude/plans/plan.yaml")
        assert exit_code == -1
        assert "no such file" in stderr


# ─── execute_plan node ────────────────────────────────────────────────────────


class TestExecutePlan:
    def test_returns_empty_when_no_plan_path(self):
        state = _make_state(plan_path=None)
        result = execute_plan(state)
        assert result == {}

    def test_returns_cost_and_tokens_from_usage_report(self, tmp_path, monkeypatch):
        plan_file = tmp_path / "01-bug.yaml"
        _write_plan(plan_file, name="Bug Fix Plan")

        report_file = tmp_path / "bug-fix-plan-usage-report.json"
        _write_usage_report(report_file, cost=0.55, input_tok=10000, output_tok=4000)

        monkeypatch.setattr(execute_plan_mod, "TASK_LOG_DIR", tmp_path)

        state = _make_state(plan_path=str(plan_file))
        with patch(
            "langgraph_pipeline.pipeline.nodes.execute_plan._spawn_orchestrator",  # module path
            return_value=(0, "Result: SUCCESS", ""),
        ):
            result = execute_plan(state)

        assert result["session_cost_usd"] == pytest.approx(0.55)
        assert result["session_input_tokens"] == 10000
        assert result["session_output_tokens"] == 4000

    def test_returns_zeros_when_usage_report_missing(self, tmp_path, monkeypatch):
        plan_file = tmp_path / "01-bug.yaml"
        _write_plan(plan_file)

        monkeypatch.setattr(execute_plan_mod, "TASK_LOG_DIR", tmp_path)

        state = _make_state(plan_path=str(plan_file))
        with patch(
            "langgraph_pipeline.pipeline.nodes.execute_plan._spawn_orchestrator",  # module path
            return_value=(0, "done", ""),
        ):
            result = execute_plan(state)

        assert result["session_cost_usd"] == 0.0
        assert result["session_input_tokens"] == 0
        assert result["session_output_tokens"] == 0

    def test_still_returns_cost_on_orchestrator_failure(self, tmp_path, monkeypatch):
        """Even when the orchestrator exits non-zero, cost data is captured."""
        plan_file = tmp_path / "01-bug.yaml"
        _write_plan(plan_file, name="Partial Plan")

        report_file = tmp_path / "partial-plan-usage-report.json"
        _write_usage_report(report_file, cost=0.20, input_tok=3000, output_tok=1000)

        monkeypatch.setattr(execute_plan_mod, "TASK_LOG_DIR", tmp_path)

        state = _make_state(plan_path=str(plan_file))
        with patch(
            "langgraph_pipeline.pipeline.nodes.execute_plan._spawn_orchestrator",  # module path
            return_value=(1, "", "task failed"),
        ):
            result = execute_plan(state)

        assert result["session_cost_usd"] == pytest.approx(0.20)

    def test_sets_rate_limited_when_rate_limit_detected(self, tmp_path, monkeypatch):
        plan_file = tmp_path / "01-bug.yaml"
        _write_plan(plan_file)
        monkeypatch.setattr(execute_plan_mod, "TASK_LOG_DIR", tmp_path)
        rate_limit_output = (
            "You've hit your limit · resets Feb 9 at 6pm (America/Toronto)"
        )
        state = _make_state(plan_path=str(plan_file))
        with patch(
            "langgraph_pipeline.pipeline.nodes.execute_plan._spawn_orchestrator",  # module path
            return_value=(1, rate_limit_output, ""),
        ):
            result = execute_plan(state)

        assert result.get("rate_limited") is True

    def test_rate_limit_reset_iso_string_is_set(self, tmp_path, monkeypatch):
        plan_file = tmp_path / "01-bug.yaml"
        _write_plan(plan_file)
        monkeypatch.setattr(execute_plan_mod, "TASK_LOG_DIR", tmp_path)
        rate_limit_output = (
            "You've hit your limit · resets Feb 9 at 6pm (America/Toronto)"
        )
        state = _make_state(plan_path=str(plan_file))
        with patch(
            "langgraph_pipeline.pipeline.nodes.execute_plan._spawn_orchestrator",  # module path
            return_value=(1, rate_limit_output, ""),
        ):
            result = execute_plan(state)

        # rate_limit_reset should be an ISO string or None when unparseable.
        assert "rate_limit_reset" in result
