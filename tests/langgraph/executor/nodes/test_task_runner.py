# tests/langgraph/executor/nodes/test_task_runner.py
# Unit tests for the execute_task executor node.
# Design: docs/plans/2026-02-26-05-task-execution-subgraph-design.md

"""Tests for langgraph_pipeline.executor.nodes.task_runner."""

import json
import os
from unittest.mock import MagicMock, patch

import pytest
import yaml

from langgraph_pipeline.executor.nodes.task_runner import (
    MODEL_TIER_TO_CLI_NAME,
    _STATUS_COMPLETED,
    _STATUS_FAILED,
    _STATUS_SUSPENDED,
    _build_child_env,
    _build_prompt,
    _find_section_for_task,
    _find_task_by_id,
    _load_agent_definition,
    _parse_agent_frontmatter,
    _read_status_file,
    _save_plan_yaml,
    execute_task,
)

# ─── Fixtures ─────────────────────────────────────────────────────────────────


def _make_state(**overrides) -> dict:
    """Build a minimal TaskState dict for tests."""
    base = {
        "plan_path": "",
        "plan_data": None,
        "current_task_id": None,
        "task_attempt": 1,
        "task_results": [],
        "effective_model": "sonnet",
        "consecutive_failures": 0,
        "last_validation_verdict": None,
        "plan_cost_usd": 0.0,
        "plan_input_tokens": 0,
        "plan_output_tokens": 0,
    }
    base.update(overrides)
    return base


def _make_plan(*tasks) -> dict:
    """Build a minimal plan dict with one section."""
    return {
        "meta": {"name": "Test Plan", "plan_doc": "docs/design.md"},
        "sections": [{"id": "s1", "name": "Section 1", "tasks": list(tasks)}],
    }


def _make_task(task_id: str, status: str = "pending", agent: str = "coder") -> dict:
    """Build a minimal task dict."""
    return {
        "id": task_id,
        "name": f"Task {task_id}",
        "status": status,
        "agent": agent,
        "description": f"Description for {task_id}",
    }


# ─── Tests: _parse_agent_frontmatter ─────────────────────────────────────────


class TestParseAgentFrontmatter:
    """_parse_agent_frontmatter extracts YAML frontmatter from markdown."""

    def test_valid_frontmatter(self):
        content = "---\nname: coder\nmodel: sonnet\n---\n# Body here"
        fm, body = _parse_agent_frontmatter(content)
        assert fm == {"name": "coder", "model": "sonnet"}
        assert "Body here" in body

    def test_no_frontmatter_returns_empty_dict(self):
        content = "# Just a body\nno frontmatter"
        fm, body = _parse_agent_frontmatter(content)
        assert fm == {}
        assert body == content

    def test_invalid_yaml_returns_empty_dict(self):
        content = "---\n: invalid: yaml:\n---\n# Body"
        fm, body = _parse_agent_frontmatter(content)
        assert fm == {}

    def test_strips_leading_newline_from_body(self):
        content = "---\nname: x\n---\n\n# Body"
        _, body = _parse_agent_frontmatter(content)
        assert body.startswith("# Body")


# ─── Tests: _load_agent_definition ───────────────────────────────────────────


class TestLoadAgentDefinition:
    """_load_agent_definition reads and parses an agent .md file."""

    def test_returns_none_for_missing_file(self, tmp_path):
        result = _load_agent_definition("missing_agent", str(tmp_path))
        assert result is None

    def test_loads_valid_agent(self, tmp_path):
        agent_file = tmp_path / "coder.md"
        agent_file.write_text("---\nname: coder\nmodel: sonnet\n---\n# Coder Role\n")
        result = _load_agent_definition("coder", str(tmp_path))
        assert result is not None
        assert result["name"] == "coder"
        assert result["model"] == "sonnet"
        assert "Coder Role" in result["body"]

    def test_fallback_name_from_filename(self, tmp_path):
        agent_file = tmp_path / "my_agent.md"
        agent_file.write_text("---\nmodel: haiku\n---\n# Body\n")
        result = _load_agent_definition("my_agent", str(tmp_path))
        assert result is not None
        assert result["name"] == "my_agent"


# ─── Tests: _find_task_by_id ─────────────────────────────────────────────────


class TestFindTaskById:
    """_find_task_by_id searches all sections for a task."""

    def test_finds_task_in_first_section(self):
        plan = _make_plan(_make_task("1.1"), _make_task("1.2"))
        assert _find_task_by_id(plan, "1.1") is not None
        assert _find_task_by_id(plan, "1.1")["id"] == "1.1"

    def test_finds_task_in_later_section(self):
        plan = {
            "sections": [
                {"tasks": [_make_task("1.1")]},
                {"tasks": [_make_task("2.1")]},
            ]
        }
        assert _find_task_by_id(plan, "2.1") is not None

    def test_returns_none_when_not_found(self):
        plan = _make_plan(_make_task("1.1"))
        assert _find_task_by_id(plan, "9.9") is None

    def test_returns_none_for_empty_plan(self):
        assert _find_task_by_id({}, "1.1") is None


# ─── Tests: _find_section_for_task ───────────────────────────────────────────


class TestFindSectionForTask:
    """_find_section_for_task returns the containing section."""

    def test_finds_correct_section(self):
        plan = {
            "sections": [
                {"id": "s1", "tasks": [_make_task("1.1")]},
                {"id": "s2", "tasks": [_make_task("2.1")]},
            ]
        }
        section = _find_section_for_task(plan, "2.1")
        assert section is not None
        assert section["id"] == "s2"

    def test_returns_none_when_task_absent(self):
        plan = _make_plan(_make_task("1.1"))
        assert _find_section_for_task(plan, "9.9") is None


# ─── Tests: _save_plan_yaml ───────────────────────────────────────────────────


class TestSavePlanYaml:
    """_save_plan_yaml writes plan dict to disk as YAML."""

    def test_round_trips_plan_data(self, tmp_path):
        plan = _make_plan(_make_task("1.1"))
        plan_path = str(tmp_path / "plan.yaml")
        _save_plan_yaml(plan_path, plan)
        with open(plan_path) as f:
            loaded = yaml.safe_load(f)
        assert loaded["meta"]["name"] == "Test Plan"


# ─── Tests: _build_child_env ─────────────────────────────────────────────────


class TestBuildChildEnv:
    """_build_child_env strips CLAUDECODE from the environment."""

    def test_strips_claudecode(self):
        with patch.dict(os.environ, {"CLAUDECODE": "1", "PATH": "/usr/bin"}):
            env = _build_child_env()
        assert "CLAUDECODE" not in env
        assert "PATH" in env

    def test_no_error_when_claudecode_absent(self):
        env_without_cc = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
        with patch.dict(os.environ, env_without_cc, clear=True):
            env = _build_child_env()
        assert "CLAUDECODE" not in env


# ─── Tests: _read_status_file ────────────────────────────────────────────────


class TestReadStatusFile:
    """_read_status_file reads and parses task-status.json."""

    def test_returns_none_when_file_missing(self, tmp_path):
        with patch(
            "langgraph_pipeline.executor.nodes.task_runner.STATUS_FILE_PATH",
            str(tmp_path / "no_file.json"),
        ):
            assert _read_status_file() is None

    def test_returns_dict_for_valid_json(self, tmp_path):
        status_file = tmp_path / "task-status.json"
        status_file.write_text('{"status": "completed", "task_id": "1.1"}')
        with patch(
            "langgraph_pipeline.executor.nodes.task_runner.STATUS_FILE_PATH",
            str(status_file),
        ):
            result = _read_status_file()
        assert result == {"status": "completed", "task_id": "1.1"}

    def test_returns_none_for_invalid_json(self, tmp_path):
        status_file = tmp_path / "task-status.json"
        status_file.write_text("not json {")
        with patch(
            "langgraph_pipeline.executor.nodes.task_runner.STATUS_FILE_PATH",
            str(status_file),
        ):
            assert _read_status_file() is None


# ─── Tests: _build_prompt ─────────────────────────────────────────────────────


class TestBuildPrompt:
    """_build_prompt assembles the Claude CLI prompt string."""

    def _run(self, task_attempt=1, validation_findings="", agent="coder", tmp_path=None):
        plan = _make_plan(_make_task("1.1", agent=agent))
        task = plan["sections"][0]["tasks"][0]
        task["validation_findings"] = validation_findings
        section = plan["sections"][0]
        agents_dir = str(tmp_path) if tmp_path else "/nonexistent"
        return _build_prompt(plan, section, task, "plan.yaml", task_attempt, "pnpm build", agents_dir)

    def test_includes_task_id(self):
        prompt = self._run()
        assert "1.1" in prompt

    def test_fresh_start_message_on_attempt_1(self):
        prompt = self._run(task_attempt=1)
        assert "fresh start" in prompt

    def test_retry_message_on_attempt_2(self):
        prompt = self._run(task_attempt=2)
        assert "attempt 2" in prompt

    def test_validation_findings_included(self):
        prompt = self._run(validation_findings="Missing tests")
        assert "PREVIOUS VALIDATION FAILED" in prompt
        assert "Missing tests" in prompt

    def test_no_validation_header_when_empty(self):
        prompt = self._run(validation_findings="")
        assert "PREVIOUS VALIDATION FAILED" not in prompt

    def test_build_command_included(self):
        prompt = self._run()
        assert "pnpm build" in prompt

    def test_agent_body_prepended_when_found(self, tmp_path):
        agent_file = tmp_path / "coder.md"
        agent_file.write_text("---\nname: coder\n---\n# Coder Instructions\n")
        prompt = self._run(tmp_path=tmp_path)
        assert "Coder Instructions" in prompt

    def test_no_agent_body_when_file_missing(self):
        prompt = self._run()
        # Should still produce a valid prompt without agent content
        assert "Run task" in prompt


# ─── Tests: execute_task node ────────────────────────────────────────────────


def _make_popen_mock(returncode: int = 0) -> MagicMock:
    """Build a Popen mock that exits immediately with the given return code."""
    proc = MagicMock()
    proc.returncode = returncode
    proc.stdout = MagicMock()
    proc.stderr = MagicMock()
    proc.poll.return_value = returncode  # already exited
    return proc


class TestExecuteTask:
    """execute_task is the main node for running a task via Claude CLI."""

    def _patch_all(
        self,
        tmp_path,
        *,
        returncode: int = 0,
        status_content: dict | None = None,
        result_capture: dict | None = None,
    ):
        """Return a set of patches for a typical execute_task test."""
        status_path = tmp_path / "task-status.json"
        if status_content is not None:
            status_path.write_text(json.dumps(status_content))

        rc = result_capture or {
            "total_cost_usd": 0.05,
            "usage": {"input_tokens": 100, "output_tokens": 50},
        }

        patches = [
            patch(
                "langgraph_pipeline.executor.nodes.task_runner.STATUS_FILE_PATH",
                str(status_path),
            ),
            patch("langgraph_pipeline.executor.nodes.task_runner._run_claude") ,
            patch("langgraph_pipeline.executor.nodes.task_runner.git_commit_files"),
            patch("langgraph_pipeline.executor.nodes.task_runner.load_orchestrator_config",
                  return_value={"agents_dir": str(tmp_path / "agents"), "build_command": "echo ok"}),
        ]
        return patches, rc

    def test_returns_empty_when_no_task_id(self, tmp_path):
        plan = _make_plan(_make_task("1.1"))
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(yaml.dump(plan))
        state = _make_state(plan_path=str(plan_file), plan_data=plan, current_task_id=None)

        result = execute_task(state)

        assert result == {}

    def test_marks_task_in_progress_before_running(self, tmp_path):
        plan = _make_plan(_make_task("1.1"))
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(yaml.dump(plan))

        status_file = tmp_path / "task-status.json"
        status_file.write_text(json.dumps({"status": "completed", "message": "done"}))

        with (
            patch("langgraph_pipeline.executor.nodes.task_runner.STATUS_FILE_PATH", str(status_file)),
            patch("langgraph_pipeline.executor.nodes.task_runner._run_claude",
                  return_value=(True, {"total_cost_usd": 0.0, "usage": {}}, "", "")),
            patch("langgraph_pipeline.executor.nodes.task_runner.git_commit_files"),
            patch("langgraph_pipeline.executor.nodes.task_runner.load_orchestrator_config",
                  return_value={"agents_dir": str(tmp_path), "build_command": "echo ok"}),
        ):
            plan_data = yaml.safe_load(plan_file.read_text())
            state = _make_state(
                plan_path=str(plan_file),
                plan_data=plan_data,
                current_task_id="1.1",
            )
            execute_task(state)

        # After execution, plan on disk should reflect completed
        saved = yaml.safe_load(plan_file.read_text())
        task = saved["sections"][0]["tasks"][0]
        assert task["status"] == "completed"

    def test_successful_task_resets_consecutive_failures(self, tmp_path):
        plan = _make_plan(_make_task("1.1"))
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(yaml.dump(plan))

        status_file = tmp_path / "task-status.json"
        status_file.write_text(json.dumps({"status": "completed", "message": "done"}))

        with (
            patch("langgraph_pipeline.executor.nodes.task_runner.STATUS_FILE_PATH", str(status_file)),
            patch("langgraph_pipeline.executor.nodes.task_runner._run_claude",
                  return_value=(True, {"total_cost_usd": 0.01, "usage": {"input_tokens": 10, "output_tokens": 5}}, "", "")),
            patch("langgraph_pipeline.executor.nodes.task_runner.git_commit_files"),
            patch("langgraph_pipeline.executor.nodes.task_runner.load_orchestrator_config",
                  return_value={"agents_dir": str(tmp_path), "build_command": "echo ok"}),
        ):
            plan_data = yaml.safe_load(plan_file.read_text())
            state = _make_state(
                plan_path=str(plan_file),
                plan_data=plan_data,
                current_task_id="1.1",
                consecutive_failures=2,
            )
            result = execute_task(state)

        assert result["consecutive_failures"] == 0

    def test_failed_task_increments_consecutive_failures(self, tmp_path):
        plan = _make_plan(_make_task("1.1"))
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(yaml.dump(plan))

        status_file = tmp_path / "task-status.json"
        status_file.write_text(json.dumps({"status": "failed", "message": "err"}))

        with (
            patch("langgraph_pipeline.executor.nodes.task_runner.STATUS_FILE_PATH", str(status_file)),
            patch("langgraph_pipeline.executor.nodes.task_runner._run_claude",
                  return_value=(False, {}, "", "error")),
            patch("langgraph_pipeline.executor.nodes.task_runner.git_commit_files"),
            patch("langgraph_pipeline.executor.nodes.task_runner.load_orchestrator_config",
                  return_value={"agents_dir": str(tmp_path), "build_command": "echo ok"}),
        ):
            plan_data = yaml.safe_load(plan_file.read_text())
            state = _make_state(
                plan_path=str(plan_file),
                plan_data=plan_data,
                current_task_id="1.1",
                consecutive_failures=1,
            )
            result = execute_task(state)

        assert result["consecutive_failures"] == 2

    def test_no_status_file_counts_as_failure(self, tmp_path):
        plan = _make_plan(_make_task("1.1"))
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(yaml.dump(plan))

        # Status file is absent
        absent_path = tmp_path / "no_status.json"

        with (
            patch("langgraph_pipeline.executor.nodes.task_runner.STATUS_FILE_PATH", str(absent_path)),
            patch("langgraph_pipeline.executor.nodes.task_runner._run_claude",
                  return_value=(True, {}, "", "")),
            patch("langgraph_pipeline.executor.nodes.task_runner.git_commit_files"),
            patch("langgraph_pipeline.executor.nodes.task_runner.load_orchestrator_config",
                  return_value={"agents_dir": str(tmp_path), "build_command": "echo ok"}),
        ):
            plan_data = yaml.safe_load(plan_file.read_text())
            state = _make_state(
                plan_path=str(plan_file),
                plan_data=plan_data,
                current_task_id="1.1",
            )
            result = execute_task(state)

        assert result["consecutive_failures"] == 1
        assert result["task_results"][0]["status"] == "failed"

    def test_accumulates_cost_and_tokens(self, tmp_path):
        plan = _make_plan(_make_task("1.1"))
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(yaml.dump(plan))

        status_file = tmp_path / "task-status.json"
        status_file.write_text(json.dumps({"status": "completed", "message": "done"}))

        rc = {"total_cost_usd": 0.10, "usage": {"input_tokens": 200, "output_tokens": 100}}

        with (
            patch("langgraph_pipeline.executor.nodes.task_runner.STATUS_FILE_PATH", str(status_file)),
            patch("langgraph_pipeline.executor.nodes.task_runner._run_claude",
                  return_value=(True, rc, "", "")),
            patch("langgraph_pipeline.executor.nodes.task_runner.git_commit_files"),
            patch("langgraph_pipeline.executor.nodes.task_runner.load_orchestrator_config",
                  return_value={"agents_dir": str(tmp_path), "build_command": "echo ok"}),
        ):
            plan_data = yaml.safe_load(plan_file.read_text())
            state = _make_state(
                plan_path=str(plan_file),
                plan_data=plan_data,
                current_task_id="1.1",
                plan_cost_usd=0.05,
                plan_input_tokens=50,
                plan_output_tokens=25,
            )
            result = execute_task(state)

        assert abs(result["plan_cost_usd"] - 0.15) < 1e-9
        assert result["plan_input_tokens"] == 250
        assert result["plan_output_tokens"] == 125

    def test_returns_task_result_in_list(self, tmp_path):
        plan = _make_plan(_make_task("1.1"))
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(yaml.dump(plan))

        status_file = tmp_path / "task-status.json"
        status_file.write_text(json.dumps({"status": "completed", "message": "all good"}))

        with (
            patch("langgraph_pipeline.executor.nodes.task_runner.STATUS_FILE_PATH", str(status_file)),
            patch("langgraph_pipeline.executor.nodes.task_runner._run_claude",
                  return_value=(True, {}, "", "")),
            patch("langgraph_pipeline.executor.nodes.task_runner.git_commit_files"),
            patch("langgraph_pipeline.executor.nodes.task_runner.load_orchestrator_config",
                  return_value={"agents_dir": str(tmp_path), "build_command": "echo ok"}),
        ):
            plan_data = yaml.safe_load(plan_file.read_text())
            state = _make_state(
                plan_path=str(plan_file),
                plan_data=plan_data,
                current_task_id="1.1",
            )
            result = execute_task(state)

        assert len(result["task_results"]) == 1
        tr = result["task_results"][0]
        assert tr["task_id"] == "1.1"
        assert tr["status"] == "completed"
        assert tr["message"] == "all good"

    def test_git_commit_called_on_success(self, tmp_path):
        plan = _make_plan(_make_task("1.1"))
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(yaml.dump(plan))

        status_file = tmp_path / "task-status.json"
        status_file.write_text(json.dumps({"status": "completed", "message": "done"}))

        with (
            patch("langgraph_pipeline.executor.nodes.task_runner.STATUS_FILE_PATH", str(status_file)),
            patch("langgraph_pipeline.executor.nodes.task_runner._run_claude",
                  return_value=(True, {}, "", "")),
            patch("langgraph_pipeline.executor.nodes.task_runner.git_commit_files") as mock_commit,
            patch("langgraph_pipeline.executor.nodes.task_runner.load_orchestrator_config",
                  return_value={"agents_dir": str(tmp_path), "build_command": "echo ok"}),
        ):
            plan_data = yaml.safe_load(plan_file.read_text())
            state = _make_state(
                plan_path=str(plan_file),
                plan_data=plan_data,
                current_task_id="1.1",
            )
            execute_task(state)

        mock_commit.assert_called_once()
        call_args = mock_commit.call_args
        assert str(plan_file) in call_args[0][0]

    def test_git_commit_not_called_on_failure(self, tmp_path):
        plan = _make_plan(_make_task("1.1"))
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(yaml.dump(plan))

        status_file = tmp_path / "task-status.json"
        status_file.write_text(json.dumps({"status": "failed", "message": "err"}))

        with (
            patch("langgraph_pipeline.executor.nodes.task_runner.STATUS_FILE_PATH", str(status_file)),
            patch("langgraph_pipeline.executor.nodes.task_runner._run_claude",
                  return_value=(False, {}, "", "")),
            patch("langgraph_pipeline.executor.nodes.task_runner.git_commit_files") as mock_commit,
            patch("langgraph_pipeline.executor.nodes.task_runner.load_orchestrator_config",
                  return_value={"agents_dir": str(tmp_path), "build_command": "echo ok"}),
        ):
            plan_data = yaml.safe_load(plan_file.read_text())
            state = _make_state(
                plan_path=str(plan_file),
                plan_data=plan_data,
                current_task_id="1.1",
            )
            execute_task(state)

        mock_commit.assert_not_called()

    def test_suspended_task_calls_interrupt(self, tmp_path):
        plan = _make_plan(_make_task("1.1"))
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(yaml.dump(plan))

        status_file = tmp_path / "task-status.json"
        status_file.write_text(json.dumps({"status": "suspended", "message": "need input"}))

        with (
            patch("langgraph_pipeline.executor.nodes.task_runner.STATUS_FILE_PATH", str(status_file)),
            patch("langgraph_pipeline.executor.nodes.task_runner._run_claude",
                  return_value=(False, {}, "", "")),
            patch("langgraph_pipeline.executor.nodes.task_runner.git_commit_files"),
            patch("langgraph_pipeline.executor.nodes.task_runner.load_orchestrator_config",
                  return_value={"agents_dir": str(tmp_path), "build_command": "echo ok"}),
            patch("langgraph_pipeline.executor.nodes.task_runner.interrupt") as mock_interrupt,
        ):
            plan_data = yaml.safe_load(plan_file.read_text())
            state = _make_state(
                plan_path=str(plan_file),
                plan_data=plan_data,
                current_task_id="1.1",
            )
            execute_task(state)

        mock_interrupt.assert_called_once_with({"task_id": "1.1", "message": "need input"})

    def test_task_not_in_plan_returns_failure(self, tmp_path):
        plan = _make_plan(_make_task("1.1"))
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(yaml.dump(plan))

        with (
            patch("langgraph_pipeline.executor.nodes.task_runner._run_claude",
                  return_value=(False, {}, "", "")),
            patch("langgraph_pipeline.executor.nodes.task_runner.git_commit_files"),
            patch("langgraph_pipeline.executor.nodes.task_runner.load_orchestrator_config",
                  return_value={}),
        ):
            plan_data = yaml.safe_load(plan_file.read_text())
            state = _make_state(
                plan_path=str(plan_file),
                plan_data=plan_data,
                current_task_id="9.9",  # does not exist
            )
            result = execute_task(state)

        assert result["consecutive_failures"] == 1
        assert result["task_results"][0]["status"] == "failed"

    def test_model_tier_maps_to_cli_name(self):
        """MODEL_TIER_TO_CLI_NAME contains entries for all three tiers."""
        assert "haiku" in MODEL_TIER_TO_CLI_NAME
        assert "sonnet" in MODEL_TIER_TO_CLI_NAME
        assert "opus" in MODEL_TIER_TO_CLI_NAME

    def test_increments_task_attempts_in_plan(self, tmp_path):
        plan = _make_plan(_make_task("1.1"))
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(yaml.dump(plan))

        status_file = tmp_path / "task-status.json"
        status_file.write_text(json.dumps({"status": "completed", "message": "ok"}))

        with (
            patch("langgraph_pipeline.executor.nodes.task_runner.STATUS_FILE_PATH", str(status_file)),
            patch("langgraph_pipeline.executor.nodes.task_runner._run_claude",
                  return_value=(True, {}, "", "")),
            patch("langgraph_pipeline.executor.nodes.task_runner.git_commit_files"),
            patch("langgraph_pipeline.executor.nodes.task_runner.load_orchestrator_config",
                  return_value={"agents_dir": str(tmp_path), "build_command": "echo ok"}),
        ):
            plan_data = yaml.safe_load(plan_file.read_text())
            state = _make_state(
                plan_path=str(plan_file),
                plan_data=plan_data,
                current_task_id="1.1",
            )
            execute_task(state)

        saved = yaml.safe_load(plan_file.read_text())
        task = saved["sections"][0]["tasks"][0]
        assert task.get("attempts", 0) >= 1
