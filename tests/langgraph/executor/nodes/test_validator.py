# tests/langgraph/executor/nodes/test_validator.py
# Unit tests for the validate_task executor node.
# Design: docs/plans/2026-02-26-05-task-execution-subgraph-design.md

"""Tests for langgraph_pipeline.executor.nodes.validator."""

import json
import os
from unittest.mock import patch

import pytest
import yaml

from langgraph_pipeline.executor.nodes.validator import (
    MODEL_TIER_TO_CLI_NAME,
    _TASK_STATUS_COMPLETED,
    _build_child_env,
    _build_validator_prompt,
    _clear_status_file,
    _find_task_by_id,
    _load_agent_body,
    _parse_verdict,
    _read_status_file,
    _save_plan_yaml,
    validate_task,
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


def _make_plan_with_validation(*tasks, enabled: bool = True) -> dict:
    """Build a plan dict with validation config and one section."""
    return {
        "meta": {
            "name": "Test Plan",
            "plan_doc": "docs/design.md",
            "source_item": "docs/feature-backlog/test.md",
            "validation": {
                "enabled": enabled,
                "run_after": ["coder", "frontend-coder"],
                "validators": ["validator"],
                "max_validation_attempts": 2,
            },
        },
        "sections": [{"id": "s1", "name": "Section 1", "tasks": list(tasks)}],
    }


def _make_task(
    task_id: str,
    status: str = _TASK_STATUS_COMPLETED,
    agent: str = "coder",
    **extra,
) -> dict:
    """Build a minimal task dict."""
    task = {
        "id": task_id,
        "name": f"Task {task_id}",
        "status": status,
        "agent": agent,
        "description": f"Description for {task_id}",
        "result_message": "Task completed successfully",
    }
    task.update(extra)
    return task


# ─── Tests: _find_task_by_id ──────────────────────────────────────────────────


class TestFindTaskById:
    """_find_task_by_id searches all sections."""

    def test_finds_task(self):
        plan = _make_plan_with_validation(_make_task("1.1"))
        assert _find_task_by_id(plan, "1.1") is not None

    def test_returns_none_when_missing(self):
        plan = _make_plan_with_validation(_make_task("1.1"))
        assert _find_task_by_id(plan, "9.9") is None

    def test_returns_none_for_empty_plan(self):
        assert _find_task_by_id({}, "1.1") is None


# ─── Tests: _save_plan_yaml ───────────────────────────────────────────────────


class TestSavePlanYaml:
    """_save_plan_yaml writes plan dict to disk."""

    def test_round_trips(self, tmp_path):
        plan = _make_plan_with_validation(_make_task("1.1"))
        path = str(tmp_path / "plan.yaml")
        _save_plan_yaml(path, plan)
        loaded = yaml.safe_load(open(path).read())
        assert loaded["meta"]["name"] == "Test Plan"


# ─── Tests: _load_agent_body ──────────────────────────────────────────────────


class TestLoadAgentBody:
    """_load_agent_body returns agent body text, stripping frontmatter."""

    def test_returns_empty_string_when_file_missing(self, tmp_path):
        result = _load_agent_body("no_agent", str(tmp_path))
        assert result == ""

    def test_returns_body_without_frontmatter(self, tmp_path):
        agent_file = tmp_path / "validator.md"
        agent_file.write_text("---\nname: validator\n---\n# Validator Role\n")
        result = _load_agent_body("validator", str(tmp_path))
        assert "Validator Role" in result
        assert "name:" not in result

    def test_returns_full_content_when_no_frontmatter(self, tmp_path):
        agent_file = tmp_path / "validator.md"
        agent_file.write_text("# Validator Role\nBody text.")
        result = _load_agent_body("validator", str(tmp_path))
        assert "Validator Role" in result

    def test_strips_leading_newline_after_frontmatter(self, tmp_path):
        agent_file = tmp_path / "validator.md"
        agent_file.write_text("---\nname: v\n---\n\n# Body")
        result = _load_agent_body("validator", str(tmp_path))
        assert result.startswith("# Body")


# ─── Tests: _build_validator_prompt ──────────────────────────────────────────


class TestBuildValidatorPrompt:
    """_build_validator_prompt assembles the validator prompt."""

    def _run(self, **task_overrides) -> str:
        plan = _make_plan_with_validation(_make_task("1.1", **task_overrides))
        task = plan["sections"][0]["tasks"][0]
        return _build_validator_prompt(plan, task, "pnpm build", "pnpm test")

    def test_includes_task_id(self):
        assert "1.1" in self._run()

    def test_includes_work_item(self):
        prompt = self._run()
        assert "docs/feature-backlog/test.md" in prompt

    def test_includes_result_message(self):
        prompt = self._run(result_message="All tests pass")
        assert "All tests pass" in prompt

    def test_includes_build_and_test_commands(self):
        prompt = self._run()
        assert "pnpm build" in prompt
        assert "pnpm test" in prompt

    def test_includes_status_file_instruction(self):
        prompt = self._run()
        assert "verdict" in prompt
        assert "PASS" in prompt


# ─── Tests: _clear_status_file ────────────────────────────────────────────────


class TestClearStatusFile:
    """_clear_status_file removes the status file if it exists."""

    def test_removes_existing_file(self, tmp_path):
        status_file = tmp_path / "task-status.json"
        status_file.write_text('{"status": "completed"}')
        with patch(
            "langgraph_pipeline.executor.nodes.validator.STATUS_FILE_PATH",
            str(status_file),
        ):
            _clear_status_file()
        assert not status_file.exists()

    def test_does_not_error_when_file_absent(self, tmp_path):
        absent = tmp_path / "no_file.json"
        with patch(
            "langgraph_pipeline.executor.nodes.validator.STATUS_FILE_PATH",
            str(absent),
        ):
            _clear_status_file()  # should not raise


# ─── Tests: _read_status_file ─────────────────────────────────────────────────


class TestReadStatusFile:
    """_read_status_file reads the validator's output."""

    def test_returns_none_when_missing(self, tmp_path):
        with patch(
            "langgraph_pipeline.executor.nodes.validator.STATUS_FILE_PATH",
            str(tmp_path / "no_file.json"),
        ):
            assert _read_status_file() is None

    def test_parses_valid_json(self, tmp_path):
        status_file = tmp_path / "task-status.json"
        status_file.write_text('{"verdict": "PASS", "status": "completed"}')
        with patch(
            "langgraph_pipeline.executor.nodes.validator.STATUS_FILE_PATH",
            str(status_file),
        ):
            result = _read_status_file()
        assert result == {"verdict": "PASS", "status": "completed"}

    def test_returns_none_for_invalid_json(self, tmp_path):
        status_file = tmp_path / "task-status.json"
        status_file.write_text("not json {")
        with patch(
            "langgraph_pipeline.executor.nodes.validator.STATUS_FILE_PATH",
            str(status_file),
        ):
            assert _read_status_file() is None


# ─── Tests: _parse_verdict ────────────────────────────────────────────────────


class TestParseVerdict:
    """_parse_verdict extracts PASS/WARN/FAIL from validator status data."""

    def test_returns_fail_when_no_status_dict(self):
        assert _parse_verdict(None, True) == "FAIL"

    def test_uses_explicit_verdict_field_pass(self):
        assert _parse_verdict({"verdict": "PASS"}, True) == "PASS"

    def test_uses_explicit_verdict_field_warn(self):
        assert _parse_verdict({"verdict": "WARN"}, True) == "WARN"

    def test_uses_explicit_verdict_field_fail(self):
        assert _parse_verdict({"verdict": "FAIL"}, True) == "FAIL"

    def test_verdict_field_case_insensitive(self):
        assert _parse_verdict({"verdict": "pass"}, True) == "PASS"

    def test_parses_fail_from_message(self):
        assert _parse_verdict({"message": "Verdict: FAIL, missing tests"}, False) == "FAIL"

    def test_parses_warn_from_message_when_no_fail(self):
        assert _parse_verdict({"message": "Verdict: WARN, style issues"}, False) == "WARN"

    def test_parses_pass_from_message_when_no_fail_no_warn(self):
        assert _parse_verdict({"message": "Verdict: PASS, all good"}, True) == "PASS"

    def test_message_fail_takes_priority_over_pass(self):
        assert _parse_verdict({"message": "PASS but also FAIL"}, True) == "FAIL"

    def test_fallback_to_pass_on_cli_success_and_completed(self):
        result = _parse_verdict({"status": "completed", "message": "done"}, True)
        assert result == "PASS"

    def test_fallback_returns_fail_when_cli_failed(self):
        result = _parse_verdict({"status": "completed", "message": "done"}, False)
        assert result == "FAIL"

    def test_model_tier_map_has_all_tiers(self):
        assert "haiku" in MODEL_TIER_TO_CLI_NAME
        assert "sonnet" in MODEL_TIER_TO_CLI_NAME
        assert "opus" in MODEL_TIER_TO_CLI_NAME


# ─── Tests: _build_child_env ─────────────────────────────────────────────────


class TestBuildChildEnv:
    """_build_child_env strips CLAUDECODE from the environment."""

    def test_strips_claudecode(self):
        with patch.dict(os.environ, {"CLAUDECODE": "1", "PATH": "/usr/bin"}):
            env = _build_child_env()
        assert "CLAUDECODE" not in env
        assert "PATH" in env


# ─── Tests: validate_task node ────────────────────────────────────────────────


class TestValidateTask:
    """validate_task is the main validation node."""

    def _make_plan_file(self, tmp_path, plan: dict) -> str:
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(yaml.dump(plan))
        return str(plan_file)

    def _write_status(self, tmp_path, content: dict) -> str:
        status_file = tmp_path / "task-status.json"
        status_file.write_text(json.dumps(content))
        return str(status_file)

    def test_returns_pass_when_no_task_id(self, tmp_path):
        plan = _make_plan_with_validation(_make_task("1.1"))
        plan_path = self._make_plan_file(tmp_path, plan)
        state = _make_state(plan_path=plan_path, plan_data=plan, current_task_id=None)
        result = validate_task(state)
        assert result["last_validation_verdict"] == "PASS"

    def test_returns_pass_when_validation_disabled(self, tmp_path):
        plan = _make_plan_with_validation(_make_task("1.1"), enabled=False)
        plan_path = self._make_plan_file(tmp_path, plan)
        state = _make_state(
            plan_path=plan_path, plan_data=plan, current_task_id="1.1"
        )
        result = validate_task(state)
        assert result["last_validation_verdict"] == "PASS"

    def test_returns_pass_when_task_not_found(self, tmp_path):
        plan = _make_plan_with_validation(_make_task("1.1"))
        plan_path = self._make_plan_file(tmp_path, plan)
        state = _make_state(
            plan_path=plan_path, plan_data=plan, current_task_id="9.9"
        )
        result = validate_task(state)
        assert result["last_validation_verdict"] == "PASS"

    def test_returns_pass_when_task_not_completed(self, tmp_path):
        plan = _make_plan_with_validation(_make_task("1.1", status="failed"))
        plan_path = self._make_plan_file(tmp_path, plan)
        state = _make_state(
            plan_path=plan_path, plan_data=plan, current_task_id="1.1"
        )
        result = validate_task(state)
        assert result["last_validation_verdict"] == "PASS"

    def test_returns_pass_when_agent_not_in_run_after(self, tmp_path):
        plan = _make_plan_with_validation(_make_task("1.1", agent="some-other-agent"))
        plan_path = self._make_plan_file(tmp_path, plan)
        state = _make_state(
            plan_path=plan_path, plan_data=plan, current_task_id="1.1"
        )
        result = validate_task(state)
        assert result["last_validation_verdict"] == "PASS"

    def test_returns_pass_when_max_validation_attempts_exceeded(self, tmp_path):
        task = _make_task("1.1", validation_attempts=2)
        plan = _make_plan_with_validation(task)
        plan_path = self._make_plan_file(tmp_path, plan)
        state = _make_state(
            plan_path=plan_path, plan_data=plan, current_task_id="1.1"
        )
        result = validate_task(state)
        assert result["last_validation_verdict"] == "PASS"

    def test_increments_validation_attempts_counter(self, tmp_path):
        task = _make_task("1.1", validation_attempts=2)
        plan = _make_plan_with_validation(task)
        plan_path = self._make_plan_file(tmp_path, plan)
        state = _make_state(
            plan_path=plan_path, plan_data=plan, current_task_id="1.1"
        )
        validate_task(state)
        # After exceeding max, plan is saved with incremented counter
        saved = yaml.safe_load(open(plan_path).read())
        assert saved["sections"][0]["tasks"][0]["validation_attempts"] == 3

    def test_pass_verdict_does_not_increment_task_attempt(self, tmp_path):
        plan = _make_plan_with_validation(_make_task("1.1"))
        plan_path = self._make_plan_file(tmp_path, plan)
        status_file = self._write_status(
            tmp_path, {"verdict": "PASS", "status": "completed", "message": "All good"}
        )
        with (
            patch("langgraph_pipeline.executor.nodes.validator.STATUS_FILE_PATH", str(status_file)),
            patch("langgraph_pipeline.executor.nodes.validator._run_claude",
                  return_value=(True, {})),
            patch("langgraph_pipeline.executor.nodes.validator._clear_status_file"),
            patch("langgraph_pipeline.executor.nodes.validator.load_orchestrator_config",
                  return_value={"agents_dir": str(tmp_path), "build_command": "echo ok"}),
        ):
            state = _make_state(
                plan_path=plan_path, plan_data=plan, current_task_id="1.1", task_attempt=1
            )
            result = validate_task(state)

        assert result["last_validation_verdict"] == "PASS"
        assert result["task_attempt"] == 1

    def test_warn_verdict_does_not_increment_task_attempt(self, tmp_path):
        plan = _make_plan_with_validation(_make_task("1.1"))
        plan_path = self._make_plan_file(tmp_path, plan)
        status_file = self._write_status(
            tmp_path, {"verdict": "WARN", "status": "completed", "message": "Minor issues"}
        )
        with (
            patch("langgraph_pipeline.executor.nodes.validator.STATUS_FILE_PATH", str(status_file)),
            patch("langgraph_pipeline.executor.nodes.validator._run_claude",
                  return_value=(True, {})),
            patch("langgraph_pipeline.executor.nodes.validator._clear_status_file"),
            patch("langgraph_pipeline.executor.nodes.validator.load_orchestrator_config",
                  return_value={"agents_dir": str(tmp_path), "build_command": "echo ok"}),
        ):
            state = _make_state(
                plan_path=plan_path, plan_data=plan, current_task_id="1.1", task_attempt=1
            )
            result = validate_task(state)

        assert result["last_validation_verdict"] == "WARN"
        assert result["task_attempt"] == 1

    def test_fail_verdict_increments_task_attempt(self, tmp_path):
        plan = _make_plan_with_validation(_make_task("1.1"))
        plan_path = self._make_plan_file(tmp_path, plan)
        status_file = self._write_status(
            tmp_path, {"verdict": "FAIL", "status": "completed", "message": "Tests missing"}
        )
        with (
            patch("langgraph_pipeline.executor.nodes.validator.STATUS_FILE_PATH", str(status_file)),
            patch("langgraph_pipeline.executor.nodes.validator._run_claude",
                  return_value=(True, {})),
            patch("langgraph_pipeline.executor.nodes.validator._clear_status_file"),
            patch("langgraph_pipeline.executor.nodes.validator.load_orchestrator_config",
                  return_value={"agents_dir": str(tmp_path), "build_command": "echo ok"}),
        ):
            state = _make_state(
                plan_path=plan_path, plan_data=plan, current_task_id="1.1", task_attempt=1
            )
            result = validate_task(state)

        assert result["last_validation_verdict"] == "FAIL"
        assert result["task_attempt"] == 2

    def test_fail_stores_validation_findings_on_task(self, tmp_path):
        plan = _make_plan_with_validation(_make_task("1.1"))
        plan_path = self._make_plan_file(tmp_path, plan)
        status_file = self._write_status(
            tmp_path, {"verdict": "FAIL", "status": "completed", "message": "Missing tests"}
        )
        with (
            patch("langgraph_pipeline.executor.nodes.validator.STATUS_FILE_PATH", str(status_file)),
            patch("langgraph_pipeline.executor.nodes.validator._run_claude",
                  return_value=(True, {})),
            patch("langgraph_pipeline.executor.nodes.validator._clear_status_file"),
            patch("langgraph_pipeline.executor.nodes.validator.load_orchestrator_config",
                  return_value={"agents_dir": str(tmp_path), "build_command": "echo ok"}),
        ):
            state = _make_state(
                plan_path=plan_path, plan_data=plan, current_task_id="1.1"
            )
            result = validate_task(state)

        saved = yaml.safe_load(open(plan_path).read())
        assert saved["sections"][0]["tasks"][0]["validation_findings"] == "Missing tests"

    def test_missing_status_file_returns_fail(self, tmp_path):
        plan = _make_plan_with_validation(_make_task("1.1"))
        plan_path = self._make_plan_file(tmp_path, plan)
        absent_path = tmp_path / "no_status.json"
        with (
            patch("langgraph_pipeline.executor.nodes.validator.STATUS_FILE_PATH", str(absent_path)),
            patch("langgraph_pipeline.executor.nodes.validator._run_claude",
                  return_value=(True, {})),
            patch("langgraph_pipeline.executor.nodes.validator.load_orchestrator_config",
                  return_value={"agents_dir": str(tmp_path), "build_command": "echo ok"}),
        ):
            state = _make_state(
                plan_path=plan_path, plan_data=plan, current_task_id="1.1"
            )
            result = validate_task(state)

        assert result["last_validation_verdict"] == "FAIL"
        assert result["task_attempt"] == 2

    def test_missing_status_file_stores_no_status_file_message(self, tmp_path):
        plan = _make_plan_with_validation(_make_task("1.1"))
        plan_path = self._make_plan_file(tmp_path, plan)
        absent_path = tmp_path / "no_status.json"
        with (
            patch("langgraph_pipeline.executor.nodes.validator.STATUS_FILE_PATH", str(absent_path)),
            patch("langgraph_pipeline.executor.nodes.validator._run_claude",
                  return_value=(False, {})),
            patch("langgraph_pipeline.executor.nodes.validator.load_orchestrator_config",
                  return_value={"agents_dir": str(tmp_path), "build_command": "echo ok"}),
        ):
            state = _make_state(
                plan_path=plan_path, plan_data=plan, current_task_id="1.1"
            )
            result = validate_task(state)

        saved = yaml.safe_load(open(plan_path).read())
        findings = saved["sections"][0]["tasks"][0]["validation_findings"]
        assert "No status file written by Claude" in findings

    def test_accumulates_cost_and_tokens(self, tmp_path):
        plan = _make_plan_with_validation(_make_task("1.1"))
        plan_path = self._make_plan_file(tmp_path, plan)
        status_file = self._write_status(
            tmp_path, {"verdict": "PASS", "status": "completed", "message": "ok"}
        )
        rc = {"total_cost_usd": 0.05, "usage": {"input_tokens": 100, "output_tokens": 50}}
        with (
            patch("langgraph_pipeline.executor.nodes.validator.STATUS_FILE_PATH", str(status_file)),
            patch("langgraph_pipeline.executor.nodes.validator._run_claude",
                  return_value=(True, rc)),
            patch("langgraph_pipeline.executor.nodes.validator._clear_status_file"),
            patch("langgraph_pipeline.executor.nodes.validator.load_orchestrator_config",
                  return_value={"agents_dir": str(tmp_path), "build_command": "echo ok"}),
        ):
            state = _make_state(
                plan_path=plan_path,
                plan_data=plan,
                current_task_id="1.1",
                plan_cost_usd=0.10,
                plan_input_tokens=200,
                plan_output_tokens=100,
            )
            result = validate_task(state)

        assert abs(result["plan_cost_usd"] - 0.15) < 1e-9
        assert result["plan_input_tokens"] == 300
        assert result["plan_output_tokens"] == 150

    def test_clears_status_file_before_running_claude(self, tmp_path):
        plan = _make_plan_with_validation(_make_task("1.1"))
        plan_path = self._make_plan_file(tmp_path, plan)
        status_file = self._write_status(
            tmp_path, {"verdict": "PASS", "status": "completed", "message": "ok"}
        )
        cleared_calls = []

        def fake_clear():
            cleared_calls.append(True)

        with (
            patch("langgraph_pipeline.executor.nodes.validator.STATUS_FILE_PATH", str(status_file)),
            patch("langgraph_pipeline.executor.nodes.validator._run_claude",
                  return_value=(True, {})),
            patch("langgraph_pipeline.executor.nodes.validator._clear_status_file",
                  side_effect=fake_clear),
            patch("langgraph_pipeline.executor.nodes.validator.load_orchestrator_config",
                  return_value={"agents_dir": str(tmp_path), "build_command": "echo ok"}),
        ):
            state = _make_state(
                plan_path=plan_path, plan_data=plan, current_task_id="1.1"
            )
            validate_task(state)

        assert len(cleared_calls) == 1

    def test_uses_agent_body_in_prompt(self, tmp_path):
        plan = _make_plan_with_validation(_make_task("1.1"))
        plan_path = self._make_plan_file(tmp_path, plan)
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        (agents_dir / "validator.md").write_text(
            "---\nname: validator\n---\n# Custom Validator Instructions\n"
        )
        status_file = self._write_status(
            tmp_path, {"verdict": "PASS", "status": "completed", "message": "ok"}
        )
        captured_prompts = []
        with (
            patch("langgraph_pipeline.executor.nodes.validator.STATUS_FILE_PATH", str(status_file)),
            patch("langgraph_pipeline.executor.nodes.validator._run_claude",
                  side_effect=lambda p, m: captured_prompts.append(p) or (True, {})),
            patch("langgraph_pipeline.executor.nodes.validator.load_orchestrator_config",
                  return_value={"agents_dir": str(agents_dir), "build_command": "echo ok"}),
        ):
            state = _make_state(
                plan_path=plan_path, plan_data=plan, current_task_id="1.1"
            )
            validate_task(state)

        assert len(captured_prompts) == 1
        assert "Custom Validator Instructions" in captured_prompts[0]

    def test_saves_plan_yaml_after_validation(self, tmp_path):
        plan = _make_plan_with_validation(_make_task("1.1"))
        plan_path = self._make_plan_file(tmp_path, plan)
        status_file = self._write_status(
            tmp_path, {"verdict": "PASS", "status": "completed", "message": "ok"}
        )
        with (
            patch("langgraph_pipeline.executor.nodes.validator.STATUS_FILE_PATH", str(status_file)),
            patch("langgraph_pipeline.executor.nodes.validator._run_claude",
                  return_value=(True, {})),
            patch("langgraph_pipeline.executor.nodes.validator._clear_status_file"),
            patch("langgraph_pipeline.executor.nodes.validator.load_orchestrator_config",
                  return_value={"agents_dir": str(tmp_path), "build_command": "echo ok"}),
        ):
            state = _make_state(
                plan_path=plan_path, plan_data=plan, current_task_id="1.1"
            )
            validate_task(state)

        saved = yaml.safe_load(open(plan_path).read())
        assert saved["sections"][0]["tasks"][0]["validation_attempts"] == 1

    def test_returns_plan_data_in_state(self, tmp_path):
        plan = _make_plan_with_validation(_make_task("1.1"))
        plan_path = self._make_plan_file(tmp_path, plan)
        status_file = self._write_status(
            tmp_path, {"verdict": "PASS", "status": "completed", "message": "ok"}
        )
        with (
            patch("langgraph_pipeline.executor.nodes.validator.STATUS_FILE_PATH", str(status_file)),
            patch("langgraph_pipeline.executor.nodes.validator._run_claude",
                  return_value=(True, {})),
            patch("langgraph_pipeline.executor.nodes.validator._clear_status_file"),
            patch("langgraph_pipeline.executor.nodes.validator.load_orchestrator_config",
                  return_value={"agents_dir": str(tmp_path), "build_command": "echo ok"}),
        ):
            state = _make_state(
                plan_path=plan_path, plan_data=plan, current_task_id="1.1"
            )
            result = validate_task(state)

        assert "plan_data" in result
        assert result["plan_data"] is not None
