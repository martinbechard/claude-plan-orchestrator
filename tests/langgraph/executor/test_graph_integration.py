# tests/langgraph/executor/test_graph_integration.py
# Integration tests for the executor StateGraph with mocked Claude CLI.
# Design: docs/plans/2026-02-26-05-task-execution-subgraph-design.md

"""Integration tests for langgraph_pipeline.executor.graph.

These tests compile the full executor StateGraph and run multi-task plans
through it with Claude CLI mocked at the subprocess level.  The goal is to
verify graph wiring: that routing functions connect nodes correctly, cost
accumulators aggregate, and the graph terminates when all tasks complete or
the circuit breaker opens.

Claude CLI is mocked by patching task_runner._run_claude so the tests run
without a live Claude installation.
"""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from langgraph_pipeline.executor.graph import build_executor_graph
from langgraph_pipeline.shared.paths import STATUS_FILE_PATH

# ─── Constants ────────────────────────────────────────────────────────────────

_COST_PER_TASK = 0.01
_INPUT_TOKENS_PER_TASK = 100
_OUTPUT_TOKENS_PER_TASK = 50

# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_plan(
    *task_specs: dict,
    validation_enabled: bool = False,
    max_attempts: int = 3,
    plan_name: str = "Integration Test Plan",
) -> dict:
    """Build a minimal plan dict for integration tests.

    Args:
        *task_specs: Dicts with task fields (id, name, status, agent, etc.)
        validation_enabled: Whether the validation step is active.
        max_attempts: Max retry attempts per task.
        plan_name: Human-readable plan name.

    Returns:
        Parsed plan dict compatible with the YAML schema.
    """
    return {
        "meta": {
            "name": plan_name,
            "plan_doc": "docs/test-design.md",
            "max_attempts_default": max_attempts,
            "validation": {"enabled": validation_enabled},
        },
        "sections": [
            {
                "id": "s1",
                "name": "Section 1",
                "tasks": list(task_specs),
            }
        ],
    }


def _make_task(
    task_id: str,
    status: str = "pending",
    agent: str = "coder",
    dependencies: list | None = None,
    **extra,
) -> dict:
    """Build a minimal task dict."""
    task: dict = {
        "id": task_id,
        "name": f"Task {task_id}",
        "status": status,
        "agent": agent,
        "description": f"Description for task {task_id}",
    }
    if dependencies is not None:
        task["dependencies"] = dependencies
    task.update(extra)
    return task


def _make_initial_state(plan_path: str) -> dict:
    """Build the initial TaskState for invoking the executor subgraph."""
    return {
        "plan_path": plan_path,
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


def _make_mock_run_claude(write_status: bool = True, success: bool = True):
    """Return a mock for task_runner._run_claude.

    The mock optionally writes a completed task-status.json at STATUS_FILE_PATH
    and returns fake usage data.

    Args:
        write_status: If True, write a completed status file before returning.
        success: Controls whether Claude CLI reports success.

    Returns:
        A callable matching the (prompt, model_cli_name) -> tuple signature.
    """

    def _mock(prompt: str, model_cli_name: str) -> tuple[bool, dict, str, str]:
        if write_status:
            status_dir = os.path.dirname(STATUS_FILE_PATH)
            os.makedirs(status_dir, exist_ok=True)
            with open(STATUS_FILE_PATH, "w") as f:
                json.dump(
                    {
                        "status": "completed" if success else "failed",
                        "message": "Mock task done" if success else "Mock task failed",
                        "timestamp": "2026-01-01T00:00:00",
                    },
                    f,
                )
        result_capture = {
            "total_cost_usd": _COST_PER_TASK,
            "usage": {
                "input_tokens": _INPUT_TOKENS_PER_TASK,
                "output_tokens": _OUTPUT_TOKENS_PER_TASK,
            },
        }
        return (success, result_capture, "", "")

    return _mock


# ─── Tests ────────────────────────────────────────────────────────────────────


class TestExecutorGraphTwoSequentialTasks:
    """Executor subgraph processes two sequential tasks to completion."""

    def test_both_tasks_complete(self, tmp_path: Path) -> None:
        plan_file = tmp_path / "plan.yaml"
        plan = _make_plan(
            _make_task("1.1"),
            _make_task("1.2", dependencies=["1.1"]),
        )
        plan_file.write_text(yaml.dump(plan))

        with (
            patch(
                "langgraph_pipeline.executor.nodes.task_runner._run_claude",
                side_effect=_make_mock_run_claude(),
            ),
            patch("langgraph_pipeline.executor.nodes.task_runner.git_commit_files"),
        ):
            executor = build_executor_graph().compile()
            final_state = executor.invoke(_make_initial_state(str(plan_file)))

        assert len(final_state["task_results"]) == 2
        statuses = {r["task_id"]: r["status"] for r in final_state["task_results"]}
        assert statuses == {"1.1": "completed", "1.2": "completed"}

    def test_cost_accumulates_across_tasks(self, tmp_path: Path) -> None:
        plan_file = tmp_path / "plan.yaml"
        plan = _make_plan(_make_task("1.1"), _make_task("1.2", dependencies=["1.1"]))
        plan_file.write_text(yaml.dump(plan))

        with (
            patch(
                "langgraph_pipeline.executor.nodes.task_runner._run_claude",
                side_effect=_make_mock_run_claude(),
            ),
            patch("langgraph_pipeline.executor.nodes.task_runner.git_commit_files"),
        ):
            executor = build_executor_graph().compile()
            final_state = executor.invoke(_make_initial_state(str(plan_file)))

        expected_cost = _COST_PER_TASK * 2
        assert abs(final_state["plan_cost_usd"] - expected_cost) < 1e-9
        assert final_state["plan_input_tokens"] == _INPUT_TOKENS_PER_TASK * 2
        assert final_state["plan_output_tokens"] == _OUTPUT_TOKENS_PER_TASK * 2

    def test_plan_yaml_updated_on_disk(self, tmp_path: Path) -> None:
        plan_file = tmp_path / "plan.yaml"
        plan = _make_plan(_make_task("1.1"), _make_task("1.2", dependencies=["1.1"]))
        plan_file.write_text(yaml.dump(plan))

        with (
            patch(
                "langgraph_pipeline.executor.nodes.task_runner._run_claude",
                side_effect=_make_mock_run_claude(),
            ),
            patch("langgraph_pipeline.executor.nodes.task_runner.git_commit_files"),
        ):
            executor = build_executor_graph().compile()
            executor.invoke(_make_initial_state(str(plan_file)))

        updated = yaml.safe_load(plan_file.read_text())
        tasks = updated["sections"][0]["tasks"]
        assert all(t["status"] == "completed" for t in tasks)


class TestExecutorGraphSingleTask:
    """Executor subgraph handles a plan with a single task."""

    def test_single_task_completes(self, tmp_path: Path) -> None:
        plan_file = tmp_path / "plan.yaml"
        plan = _make_plan(_make_task("1.1"))
        plan_file.write_text(yaml.dump(plan))

        with (
            patch(
                "langgraph_pipeline.executor.nodes.task_runner._run_claude",
                side_effect=_make_mock_run_claude(),
            ),
            patch("langgraph_pipeline.executor.nodes.task_runner.git_commit_files"),
        ):
            executor = build_executor_graph().compile()
            final_state = executor.invoke(_make_initial_state(str(plan_file)))

        assert len(final_state["task_results"]) == 1
        assert final_state["task_results"][0]["status"] == "completed"
        assert final_state["consecutive_failures"] == 0


class TestExecutorGraphEmptyPlan:
    """Executor subgraph terminates immediately for an empty plan."""

    def test_empty_plan_exits_gracefully(self, tmp_path: Path) -> None:
        plan_file = tmp_path / "plan.yaml"
        plan = {
            "meta": {"name": "Empty", "validation": {"enabled": False}},
            "sections": [{"id": "s1", "name": "S1", "tasks": []}],
        }
        plan_file.write_text(yaml.dump(plan))

        executor = build_executor_graph().compile()
        final_state = executor.invoke(_make_initial_state(str(plan_file)))

        assert final_state["task_results"] == []
        assert final_state["current_task_id"] is None


class TestExecutorGraphCircuitBreaker:
    """Executor subgraph halts after DEFAULT_FAILURE_THRESHOLD consecutive failures."""

    def test_circuit_breaker_stops_after_three_failures(self, tmp_path: Path) -> None:
        plan_file = tmp_path / "plan.yaml"
        # Five tasks; circuit should open after 3 failures and stop execution.
        plan = _make_plan(
            _make_task("1.1"),
            _make_task("1.2"),
            _make_task("1.3"),
            _make_task("1.4"),
            _make_task("1.5"),
        )
        plan_file.write_text(yaml.dump(plan))

        # _run_claude always fails: writes failed status, returns success=False
        def _always_fail(prompt: str, model_cli_name: str):
            status_dir = os.path.dirname(STATUS_FILE_PATH)
            os.makedirs(status_dir, exist_ok=True)
            with open(STATUS_FILE_PATH, "w") as f:
                json.dump(
                    {"status": "failed", "message": "Task failed", "timestamp": "2026-01-01T00:00:00"},
                    f,
                )
            return (False, {}, "", "")

        with (
            patch(
                "langgraph_pipeline.executor.nodes.task_runner._run_claude",
                side_effect=_always_fail,
            ),
            patch("langgraph_pipeline.executor.nodes.task_runner.git_commit_files"),
        ):
            executor = build_executor_graph().compile()
            final_state = executor.invoke(_make_initial_state(str(plan_file)))

        # Circuit opens at 3 failures; at most 3 tasks should have been attempted.
        assert len(final_state["task_results"]) <= 3
        assert all(r["status"] == "failed" for r in final_state["task_results"])

    def test_circuit_resets_after_success(self, tmp_path: Path) -> None:
        plan_file = tmp_path / "plan.yaml"
        plan = _make_plan(_make_task("1.1"), _make_task("1.2", dependencies=["1.1"]))
        plan_file.write_text(yaml.dump(plan))

        with (
            patch(
                "langgraph_pipeline.executor.nodes.task_runner._run_claude",
                side_effect=_make_mock_run_claude(success=True),
            ),
            patch("langgraph_pipeline.executor.nodes.task_runner.git_commit_files"),
        ):
            executor = build_executor_graph().compile()
            final_state = executor.invoke(_make_initial_state(str(plan_file)))

        assert final_state["consecutive_failures"] == 0


class TestExecutorGraphCompletedTasksSkipped:
    """Executor subgraph skips tasks already in terminal states."""

    def test_pre_completed_task_is_skipped(self, tmp_path: Path) -> None:
        plan_file = tmp_path / "plan.yaml"
        plan = _make_plan(
            _make_task("1.1", status="completed"),
            _make_task("1.2", dependencies=["1.1"]),
        )
        plan_file.write_text(yaml.dump(plan))

        with (
            patch(
                "langgraph_pipeline.executor.nodes.task_runner._run_claude",
                side_effect=_make_mock_run_claude(),
            ),
            patch("langgraph_pipeline.executor.nodes.task_runner.git_commit_files"),
        ):
            executor = build_executor_graph().compile()
            final_state = executor.invoke(_make_initial_state(str(plan_file)))

        # Only 1.2 should have been executed (1.1 was already completed).
        assert len(final_state["task_results"]) == 1
        assert final_state["task_results"][0]["task_id"] == "1.2"


class TestExecutorGraphWithValidation:
    """Executor subgraph handles validation pass correctly."""

    def test_validation_pass_continues_to_next_task(self, tmp_path: Path) -> None:
        plan_file = tmp_path / "plan.yaml"
        plan = _make_plan(
            _make_task("1.1"),
            _make_task("1.2", dependencies=["1.1"]),
            validation_enabled=True,
        )
        # Set run_after to coder so validation triggers for these tasks
        plan["meta"]["validation"]["run_after"] = ["coder"]
        plan["meta"]["validation"]["validators"] = ["validator"]
        plan["meta"]["validation"]["max_validation_attempts"] = 2
        plan_file.write_text(yaml.dump(plan))

        def _mock_task_claude(prompt, model_cli_name):
            os.makedirs(os.path.dirname(STATUS_FILE_PATH), exist_ok=True)
            with open(STATUS_FILE_PATH, "w") as f:
                json.dump(
                    {"status": "completed", "message": "Done", "timestamp": "2026-01-01T00:00:00"},
                    f,
                )
            return (True, {"total_cost_usd": _COST_PER_TASK, "usage": {"input_tokens": 100, "output_tokens": 50}}, "", "")

        def _mock_validator_claude(prompt, model_cli_name):
            os.makedirs(os.path.dirname(STATUS_FILE_PATH), exist_ok=True)
            with open(STATUS_FILE_PATH, "w") as f:
                json.dump(
                    {"verdict": "PASS", "status": "completed", "message": "PASS: All good"},
                    f,
                )
            # validator._run_claude returns (success, result_capture) — a 2-tuple
            return (True, {})

        call_count = {"n": 0}

        def _mock_both_claude(prompt, model_cli_name):
            call_count["n"] += 1
            # Odd calls are task runner, even calls are validator
            if "Validate task" in prompt:
                return _mock_validator_claude(prompt, model_cli_name)
            return _mock_task_claude(prompt, model_cli_name)

        with (
            patch(
                "langgraph_pipeline.executor.nodes.task_runner._run_claude",
                side_effect=_mock_task_claude,
            ),
            patch(
                "langgraph_pipeline.executor.nodes.validator._run_claude",
                side_effect=_mock_validator_claude,
            ),
            patch("langgraph_pipeline.executor.nodes.task_runner.git_commit_files"),
        ):
            executor = build_executor_graph().compile()
            final_state = executor.invoke(_make_initial_state(str(plan_file)))

        assert len(final_state["task_results"]) == 2
        assert all(r["status"] == "completed" for r in final_state["task_results"])
