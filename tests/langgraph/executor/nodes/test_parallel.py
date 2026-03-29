# tests/langgraph/executor/nodes/test_parallel.py
# Unit tests for the parallel executor nodes (fan_out, execute_parallel_task, fan_in).
# Design: docs/plans/2026-02-26-05-task-execution-subgraph-design.md

"""Tests for langgraph_pipeline.executor.nodes.parallel."""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest
import yaml

from langgraph.types import Send

from langgraph_pipeline.executor.nodes.parallel import (
    MODEL_TIER_TO_CLI_NAME,
    PENDING_STATUS,
    WORKTREE_STATUS_FILE_RELATIVE,
    _OUTCOME_COMPLETED,
    _OUTCOME_FAILED,
    _TERMINAL_STATUSES,
    _build_child_env,
    _build_parallel_prompt,
    _collect_tasks,
    _completed_task_ids,
    _filter_exclusive_resources,
    _find_parallel_group_tasks,
    _find_section_for_task,
    _find_task_by_id,
    _load_plan_yaml,
    _read_worktree_status,
    _save_plan_yaml,
    execute_parallel_task,
    fan_in,
    fan_out,
)

# ─── Fixtures ─────────────────────────────────────────────────────────────────


def _make_state(**overrides) -> dict:
    """Build a minimal TaskState dict for tests."""
    base = {
        "plan_path": "plan.yaml",
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


def _make_task(
    task_id: str,
    status: str = "pending",
    agent: str = "coder",
    parallel_group: str = None,
    exclusive_resource: str = None,
    dependencies: list = None,
    **extra,
) -> dict:
    """Build a minimal task dict."""
    task: dict = {
        "id": task_id,
        "name": f"Task {task_id}",
        "status": status,
        "agent": agent,
        "description": f"Description for {task_id}",
    }
    if parallel_group is not None:
        task["parallel_group"] = parallel_group
    if exclusive_resource is not None:
        task["exclusive_resource"] = exclusive_resource
    if dependencies is not None:
        task["dependencies"] = dependencies
    task.update(extra)
    return task


def _make_plan(*tasks, plan_name: str = "Test Plan") -> dict:
    """Build a minimal plan dict with one section."""
    return {
        "meta": {"name": plan_name, "plan_doc": "docs/design.md"},
        "sections": [{"id": "s1", "name": "Section 1", "tasks": list(tasks)}],
    }


# ─── Tests: _find_task_by_id ──────────────────────────────────────────────────


class TestFindTaskById:
    def test_finds_existing_task(self):
        plan = _make_plan(_make_task("1.1"), _make_task("1.2"))
        assert _find_task_by_id(plan, "1.2")["id"] == "1.2"

    def test_returns_none_for_missing_task(self):
        plan = _make_plan(_make_task("1.1"))
        assert _find_task_by_id(plan, "1.9") is None

    def test_empty_plan(self):
        assert _find_task_by_id({}, "1.1") is None


# ─── Tests: _find_section_for_task ────────────────────────────────────────────


class TestFindSectionForTask:
    def test_finds_section(self):
        plan = _make_plan(_make_task("1.1"), _make_task("1.2"))
        section = _find_section_for_task(plan, "1.2")
        assert section is not None
        assert section["id"] == "s1"

    def test_returns_none_for_missing_task(self):
        plan = _make_plan(_make_task("1.1"))
        assert _find_section_for_task(plan, "9.9") is None


# ─── Tests: _collect_tasks ────────────────────────────────────────────────────


class TestCollectTasks:
    def test_collects_from_all_sections(self):
        plan = {
            "sections": [
                {"tasks": [{"id": "1.1"}, {"id": "1.2"}]},
                {"tasks": [{"id": "2.1"}]},
            ]
        }
        tasks = _collect_tasks(plan)
        assert [t["id"] for t in tasks] == ["1.1", "1.2", "2.1"]

    def test_empty_plan(self):
        assert _collect_tasks({}) == []


# ─── Tests: _completed_task_ids ───────────────────────────────────────────────


class TestCompletedTaskIds:
    # No validation: completed tasks get promoted to verified via effective_status
    _NO_VALIDATION = {}
    _VALIDATION_ENABLED = {"enabled": True, "run_after": ["coder"]}

    def test_verified_failed_skipped_included(self):
        tasks = [
            {"id": "1", "status": "verified"},
            {"id": "2", "status": "pending"},
            {"id": "3", "status": "failed"},
            {"id": "4", "status": "skipped"},
        ]
        assert _completed_task_ids(tasks, self._NO_VALIDATION) == {"1", "3", "4"}

    def test_completed_promoted_when_no_validation(self):
        tasks = [{"id": "1", "status": "completed", "agent": "coder"}]
        assert _completed_task_ids(tasks, self._NO_VALIDATION) == {"1"}

    def test_completed_blocked_when_validation_enabled(self):
        tasks = [{"id": "1", "status": "completed", "agent": "coder"}]
        assert _completed_task_ids(tasks, self._VALIDATION_ENABLED) == set()


# ─── Tests: _find_parallel_group_tasks ────────────────────────────────────────


class TestFindParallelGroupTasks:
    def test_returns_pending_tasks_in_group(self):
        plan = _make_plan(
            _make_task("1.1", parallel_group="ga"),
            _make_task("1.2", parallel_group="ga"),
            _make_task("1.3", parallel_group="gb"),
        )
        tasks = _find_parallel_group_tasks(plan, "ga")
        assert [t["id"] for t in tasks] == ["1.1", "1.2"]

    def test_excludes_non_pending_tasks(self):
        plan = _make_plan(
            _make_task("1.1", status="completed", parallel_group="ga"),
            _make_task("1.2", parallel_group="ga"),
        )
        tasks = _find_parallel_group_tasks(plan, "ga")
        assert [t["id"] for t in tasks] == ["1.2"]

    def test_excludes_tasks_with_unsatisfied_deps(self):
        plan = _make_plan(
            _make_task("1.1", parallel_group="ga"),
            _make_task("1.2", parallel_group="ga", dependencies=["1.3"]),
        )
        tasks = _find_parallel_group_tasks(plan, "ga")
        assert [t["id"] for t in tasks] == ["1.1"]

    def test_includes_tasks_with_satisfied_deps(self):
        plan = _make_plan(
            _make_task("1.0", status="completed"),
            _make_task("1.1", parallel_group="ga", dependencies=["1.0"]),
        )
        tasks = _find_parallel_group_tasks(plan, "ga")
        assert [t["id"] for t in tasks] == ["1.1"]

    def test_returns_empty_for_unknown_group(self):
        plan = _make_plan(_make_task("1.1", parallel_group="ga"))
        assert _find_parallel_group_tasks(plan, "gb") == []

    def test_completed_dep_blocks_when_validation_enabled(self):
        """Parallel group task blocked by completed (not verified) dependency."""
        plan = {
            "meta": {
                "name": "P",
                "plan_doc": "d",
                "validation": {"enabled": True, "run_after": ["coder"]},
            },
            "sections": [{
                "tasks": [
                    _make_task("1.0", status="completed", agent="coder"),
                    _make_task("1.1", parallel_group="ga", dependencies=["1.0"]),
                ],
            }],
        }
        tasks = _find_parallel_group_tasks(plan, "ga")
        assert tasks == []

    def test_verified_dep_satisfies_with_validation_enabled(self):
        """Parallel group task unblocked by verified dependency."""
        plan = {
            "meta": {
                "name": "P",
                "plan_doc": "d",
                "validation": {"enabled": True, "run_after": ["coder"]},
            },
            "sections": [{
                "tasks": [
                    _make_task("1.0", status="verified", agent="coder"),
                    _make_task("1.1", parallel_group="ga", dependencies=["1.0"]),
                ],
            }],
        }
        tasks = _find_parallel_group_tasks(plan, "ga")
        assert [t["id"] for t in tasks] == ["1.1"]


# ─── Tests: _filter_exclusive_resources ──────────────────────────────────────


class TestFilterExclusiveResources:
    def test_allows_all_when_no_exclusive_resource(self):
        tasks = [_make_task("1.1"), _make_task("1.2"), _make_task("1.3")]
        result = _filter_exclusive_resources(tasks)
        assert len(result) == 3

    def test_keeps_only_first_per_resource(self):
        tasks = [
            _make_task("1.1", exclusive_resource="db"),
            _make_task("1.2", exclusive_resource="db"),
            _make_task("1.3"),
        ]
        result = _filter_exclusive_resources(tasks)
        assert [t["id"] for t in result] == ["1.1", "1.3"]

    def test_different_resources_run_concurrently(self):
        tasks = [
            _make_task("1.1", exclusive_resource="db"),
            _make_task("1.2", exclusive_resource="cache"),
        ]
        result = _filter_exclusive_resources(tasks)
        assert len(result) == 2

    def test_empty_list(self):
        assert _filter_exclusive_resources([]) == []


# ─── Tests: _build_parallel_prompt ────────────────────────────────────────────


class TestBuildParallelPrompt:
    def _make_section(self) -> dict:
        return {"id": "s1", "name": "Section 1"}

    def test_includes_task_id_and_name(self):
        plan = _make_plan(_make_task("1.1"))
        section = self._make_section()
        task = _make_task("1.1")
        prompt = _build_parallel_prompt(plan, section, task, "plan.yaml", 1)
        assert "1.1" in prompt
        assert "Task 1.1" in prompt

    def test_fresh_start_message_on_attempt_1(self):
        plan = _make_plan(_make_task("1.1"))
        section = self._make_section()
        task = _make_task("1.1")
        prompt = _build_parallel_prompt(plan, section, task, "plan.yaml", 1)
        assert "fresh start" in prompt

    def test_retry_message_on_attempt_2(self):
        plan = _make_plan(_make_task("1.1"))
        section = self._make_section()
        task = _make_task("1.1")
        prompt = _build_parallel_prompt(plan, section, task, "plan.yaml", 2)
        assert "attempt 2" in prompt

    def test_includes_status_file_path(self):
        plan = _make_plan(_make_task("1.1"))
        section = self._make_section()
        task = _make_task("1.1")
        prompt = _build_parallel_prompt(plan, section, task, "plan.yaml", 1)
        assert WORKTREE_STATUS_FILE_RELATIVE in prompt

    def test_includes_plan_doc(self):
        plan = {
            "meta": {"name": "P", "plan_doc": "docs/my-design.md"},
            "sections": [],
        }
        section = self._make_section()
        task = _make_task("1.1")
        prompt = _build_parallel_prompt(plan, section, task, "plan.yaml", 1)
        assert "docs/my-design.md" in prompt


# ─── Tests: _build_child_env ─────────────────────────────────────────────────


class TestBuildChildEnv:
    def test_strips_claudecode(self):
        with patch.dict(os.environ, {"CLAUDECODE": "1"}):
            env = _build_child_env()
        assert "CLAUDECODE" not in env

    def test_preserves_other_vars(self):
        with patch.dict(os.environ, {"MY_VAR": "hello"}):
            env = _build_child_env()
        assert env.get("MY_VAR") == "hello"


# ─── Tests: _read_worktree_status ─────────────────────────────────────────────


class TestReadWorktreeStatus:
    def test_returns_none_when_file_missing(self, tmp_path):
        result = _read_worktree_status(tmp_path)
        assert result is None

    def test_reads_valid_json(self, tmp_path):
        status_path = tmp_path / "tmp"
        status_path.mkdir(parents=True)
        (status_path / "task-status.json").write_text(
            json.dumps({"task_id": "1.1", "status": "completed", "message": "Done"})
        )
        result = _read_worktree_status(tmp_path)
        assert result == {"task_id": "1.1", "status": "completed", "message": "Done"}

    def test_returns_none_on_invalid_json(self, tmp_path):
        status_path = tmp_path / "tmp"
        status_path.mkdir(parents=True)
        (status_path / "task-status.json").write_text("not json {{")
        result = _read_worktree_status(tmp_path)
        assert result is None


# ─── Tests: fan_out ───────────────────────────────────────────────────────────


class TestFanOut:
    def test_returns_empty_when_no_current_task_id(self):
        state = _make_state(current_task_id=None, plan_data=_make_plan())
        result = fan_out(state)
        assert result == []

    def test_returns_empty_when_task_not_found(self):
        plan = _make_plan(_make_task("1.1"))
        state = _make_state(current_task_id="9.9", plan_data=plan)
        result = fan_out(state)
        assert result == []

    def test_dispatches_single_branch_for_task_without_parallel_group(self):
        task = _make_task("1.1")
        plan = _make_plan(task)
        state = _make_state(current_task_id="1.1", plan_data=plan)
        result = fan_out(state)
        assert len(result) == 1
        assert isinstance(result[0], Send)
        assert result[0].node == "execute_parallel_task"

    def test_dispatches_all_pending_group_tasks(self):
        tasks = [
            _make_task("1.1", parallel_group="ga"),
            _make_task("1.2", parallel_group="ga"),
            _make_task("1.3", parallel_group="ga"),
        ]
        plan = _make_plan(*tasks)
        state = _make_state(current_task_id="1.1", plan_data=plan)
        result = fan_out(state)
        assert len(result) == 3
        dispatched_ids = {s.arg["current_task_id"] for s in result}
        assert dispatched_ids == {"1.1", "1.2", "1.3"}

    def test_excludes_completed_tasks_from_dispatch(self):
        tasks = [
            _make_task("1.1", parallel_group="ga"),
            _make_task("1.2", parallel_group="ga", status="completed"),
        ]
        plan = _make_plan(*tasks)
        state = _make_state(current_task_id="1.1", plan_data=plan)
        result = fan_out(state)
        assert len(result) == 1
        assert result[0].arg["current_task_id"] == "1.1"

    def test_defers_second_task_with_same_exclusive_resource(self):
        tasks = [
            _make_task("1.1", parallel_group="ga", exclusive_resource="db"),
            _make_task("1.2", parallel_group="ga", exclusive_resource="db"),
            _make_task("1.3", parallel_group="ga"),
        ]
        plan = _make_plan(*tasks)
        state = _make_state(current_task_id="1.1", plan_data=plan)
        result = fan_out(state)
        dispatched_ids = {s.arg["current_task_id"] for s in result}
        assert "1.1" in dispatched_ids
        assert "1.2" not in dispatched_ids
        assert "1.3" in dispatched_ids

    def test_returns_empty_when_no_pending_group_tasks(self):
        tasks = [
            _make_task("1.1", parallel_group="ga", status="completed"),
            _make_task("1.2", parallel_group="ga", status="failed"),
        ]
        plan = _make_plan(*tasks)
        state = _make_state(current_task_id="1.1", plan_data=plan)
        result = fan_out(state)
        assert result == []

    def test_sends_carry_full_state_context(self):
        task = _make_task("1.1", parallel_group="ga")
        plan = _make_plan(task)
        state = _make_state(
            current_task_id="1.1",
            plan_data=plan,
            effective_model="opus",
            plan_cost_usd=1.5,
        )
        result = fan_out(state)
        assert len(result) == 1
        branch_state = result[0].arg
        assert branch_state["effective_model"] == "opus"
        assert branch_state["plan_cost_usd"] == 1.5


# ─── Tests: execute_parallel_task ─────────────────────────────────────────────


class TestExecuteParallelTask:
    def _base_state(self, plan_path: str, plan_data: dict) -> dict:
        return _make_state(
            plan_path=plan_path,
            plan_data=plan_data,
            current_task_id="1.1",
            effective_model="sonnet",
        )

    @patch("langgraph_pipeline.executor.nodes.parallel._load_plan_yaml")
    @patch("langgraph_pipeline.executor.nodes.parallel.create_worktree")
    @patch("langgraph_pipeline.executor.nodes.parallel._run_claude_in_worktree")
    @patch("langgraph_pipeline.executor.nodes.parallel._read_worktree_status")
    @patch("langgraph_pipeline.executor.nodes.parallel.copy_worktree_artifacts")
    @patch("langgraph_pipeline.executor.nodes.parallel.cleanup_worktree")
    @patch("langgraph_pipeline.executor.nodes.parallel._save_plan_yaml")
    @patch("langgraph_pipeline.executor.nodes.parallel.git_commit_files")
    def test_successful_task_returns_completed_result(
        self,
        mock_commit,
        mock_save,
        mock_cleanup,
        mock_copy,
        mock_read_status,
        mock_run_claude,
        mock_create_worktree,
        mock_load_plan,
    ):
        task = _make_task("1.1")
        plan = _make_plan(task)
        mock_load_plan.return_value = plan
        mock_create_worktree.return_value = Path("/tmp/worktree-1.1")
        mock_run_claude.return_value = (
            True,
            {"total_cost_usd": 0.5, "usage": {"input_tokens": 100, "output_tokens": 50}},
        )
        mock_read_status.return_value = {"status": "completed", "message": "Done"}
        mock_copy.return_value = (True, "1 copied", ["src/foo.py"])
        mock_cleanup.return_value = True

        state = self._base_state("plan.yaml", plan)
        with patch("subprocess.run"):
            result = execute_parallel_task(state)

        assert len(result["task_results"]) == 1
        task_result = result["task_results"][0]
        assert task_result["task_id"] == "1.1"
        assert task_result["status"] == "completed"
        assert task_result["cost_usd"] == 0.5
        assert result["consecutive_failures"] == 0

    @patch("langgraph_pipeline.executor.nodes.parallel._load_plan_yaml")
    @patch("langgraph_pipeline.executor.nodes.parallel.create_worktree")
    @patch("langgraph_pipeline.executor.nodes.parallel._run_claude_in_worktree")
    @patch("langgraph_pipeline.executor.nodes.parallel._read_worktree_status")
    @patch("langgraph_pipeline.executor.nodes.parallel.copy_worktree_artifacts")
    @patch("langgraph_pipeline.executor.nodes.parallel.cleanup_worktree")
    @patch("langgraph_pipeline.executor.nodes.parallel._save_plan_yaml")
    def test_failed_claude_returns_failed_result(
        self,
        mock_save,
        mock_cleanup,
        mock_copy,
        mock_read_status,
        mock_run_claude,
        mock_create_worktree,
        mock_load_plan,
    ):
        task = _make_task("1.1")
        plan = _make_plan(task)
        mock_load_plan.return_value = plan
        mock_create_worktree.return_value = Path("/tmp/worktree-1.1")
        mock_run_claude.return_value = (False, {})
        mock_read_status.return_value = None
        mock_cleanup.return_value = True

        state = self._base_state("plan.yaml", plan)
        result = execute_parallel_task(state)

        assert result["task_results"][0]["status"] == "failed"
        assert result["task_results"][0]["message"] == "No status file written by Claude"
        assert result["consecutive_failures"] == 1

    @patch("langgraph_pipeline.executor.nodes.parallel._load_plan_yaml")
    @patch("langgraph_pipeline.executor.nodes.parallel.create_worktree")
    @patch("langgraph_pipeline.executor.nodes.parallel._save_plan_yaml")
    def test_worktree_creation_failure_returns_failed_result(
        self, mock_save, mock_create_worktree, mock_load_plan
    ):
        task = _make_task("1.1")
        plan = _make_plan(task)
        mock_load_plan.return_value = plan
        mock_create_worktree.return_value = None

        state = self._base_state("plan.yaml", plan)
        result = execute_parallel_task(state)

        assert result["task_results"][0]["status"] == "failed"
        assert result["task_results"][0]["message"] == "Failed to create git worktree"
        assert result["consecutive_failures"] == 1

    @patch("langgraph_pipeline.executor.nodes.parallel._load_plan_yaml")
    def test_missing_task_returns_failed_result(self, mock_load_plan):
        plan = _make_plan(_make_task("9.9"))
        mock_load_plan.return_value = plan

        state = _make_state(
            plan_path="plan.yaml",
            plan_data=plan,
            current_task_id="1.1",
        )
        result = execute_parallel_task(state)

        assert result["task_results"][0]["status"] == "failed"
        assert "not found" in result["task_results"][0]["message"]
        assert result["consecutive_failures"] == 1

    @patch("langgraph_pipeline.executor.nodes.parallel._load_plan_yaml")
    @patch("langgraph_pipeline.executor.nodes.parallel.create_worktree")
    @patch("langgraph_pipeline.executor.nodes.parallel._run_claude_in_worktree")
    @patch("langgraph_pipeline.executor.nodes.parallel._read_worktree_status")
    @patch("langgraph_pipeline.executor.nodes.parallel.copy_worktree_artifacts")
    @patch("langgraph_pipeline.executor.nodes.parallel.cleanup_worktree")
    @patch("langgraph_pipeline.executor.nodes.parallel._save_plan_yaml")
    def test_artifact_copy_failure_marks_task_failed(
        self,
        mock_save,
        mock_cleanup,
        mock_copy,
        mock_read_status,
        mock_run_claude,
        mock_create_worktree,
        mock_load_plan,
    ):
        task = _make_task("1.1")
        plan = _make_plan(task)
        mock_load_plan.return_value = plan
        mock_create_worktree.return_value = Path("/tmp/worktree-1.1")
        mock_run_claude.return_value = (True, {})
        mock_read_status.return_value = {"status": "completed", "message": "Done"}
        mock_copy.return_value = (False, "git diff failed", [])
        mock_cleanup.return_value = True

        state = self._base_state("plan.yaml", plan)
        result = execute_parallel_task(state)

        assert result["task_results"][0]["status"] == "failed"
        assert "Artifact copy failed" in result["task_results"][0]["message"]

    @patch("langgraph_pipeline.executor.nodes.parallel._load_plan_yaml")
    @patch("langgraph_pipeline.executor.nodes.parallel.create_worktree")
    @patch("langgraph_pipeline.executor.nodes.parallel._run_claude_in_worktree")
    @patch("langgraph_pipeline.executor.nodes.parallel._read_worktree_status")
    @patch("langgraph_pipeline.executor.nodes.parallel.copy_worktree_artifacts")
    @patch("langgraph_pipeline.executor.nodes.parallel.cleanup_worktree")
    @patch("langgraph_pipeline.executor.nodes.parallel._save_plan_yaml")
    def test_cost_accumulated_in_returned_state(
        self,
        mock_save,
        mock_cleanup,
        mock_copy,
        mock_read_status,
        mock_run_claude,
        mock_create_worktree,
        mock_load_plan,
    ):
        task = _make_task("1.1")
        plan = _make_plan(task)
        mock_load_plan.return_value = plan
        mock_create_worktree.return_value = Path("/tmp/worktree-1.1")
        mock_run_claude.return_value = (
            True,
            {
                "total_cost_usd": 1.25,
                "usage": {"input_tokens": 200, "output_tokens": 100},
            },
        )
        mock_read_status.return_value = {"status": "completed", "message": "Done"}
        mock_copy.return_value = (True, "1 copied", [])
        mock_cleanup.return_value = True

        state = _make_state(
            plan_path="plan.yaml",
            plan_data=plan,
            current_task_id="1.1",
            plan_cost_usd=0.75,
            plan_input_tokens=50,
            plan_output_tokens=25,
        )
        with patch("subprocess.run"):
            result = execute_parallel_task(state)

        assert result["plan_cost_usd"] == pytest.approx(0.75 + 1.25)
        assert result["plan_input_tokens"] == 50 + 200
        assert result["plan_output_tokens"] == 25 + 100


# ─── Tests: fan_in ────────────────────────────────────────────────────────────


class TestFanIn:
    @patch("langgraph_pipeline.executor.nodes.parallel._load_plan_yaml")
    @patch("langgraph_pipeline.executor.nodes.parallel.git_commit_files")
    def test_reloads_plan_and_commits_on_success(self, mock_commit, mock_load):
        fresh_plan = _make_plan(_make_task("1.1", status="completed"))
        mock_load.return_value = fresh_plan

        state = _make_state(
            plan_path="plan.yaml",
            task_results=[
                {
                    "task_id": "1.1",
                    "status": "completed",
                    "model": "sonnet",
                    "cost_usd": 0.5,
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "message": "Done",
                }
            ],
        )
        result = fan_in(state)

        assert result["plan_data"] is fresh_plan
        mock_commit.assert_called_once()
        commit_args = mock_commit.call_args[0]
        assert "1.1" in commit_args[1]

    @patch("langgraph_pipeline.executor.nodes.parallel._load_plan_yaml")
    @patch("langgraph_pipeline.executor.nodes.parallel.git_commit_files")
    def test_skips_commit_when_no_tasks_completed(self, mock_commit, mock_load):
        fresh_plan = _make_plan(_make_task("1.1", status="failed"))
        mock_load.return_value = fresh_plan

        state = _make_state(
            plan_path="plan.yaml",
            task_results=[
                {
                    "task_id": "1.1",
                    "status": "failed",
                    "model": "sonnet",
                    "cost_usd": 0.0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "message": "Error",
                }
            ],
        )
        fan_in(state)
        mock_commit.assert_not_called()

    @patch("langgraph_pipeline.executor.nodes.parallel._load_plan_yaml")
    @patch("langgraph_pipeline.executor.nodes.parallel.git_commit_files")
    def test_includes_all_completed_task_ids_in_commit_message(self, mock_commit, mock_load):
        mock_load.return_value = {}
        state = _make_state(
            plan_path="plan.yaml",
            task_results=[
                {
                    "task_id": "1.1",
                    "status": "completed",
                    "model": "sonnet",
                    "cost_usd": 0.0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "message": "Done",
                },
                {
                    "task_id": "1.2",
                    "status": "completed",
                    "model": "sonnet",
                    "cost_usd": 0.0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "message": "Done",
                },
                {
                    "task_id": "1.3",
                    "status": "failed",
                    "model": "sonnet",
                    "cost_usd": 0.0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "message": "Error",
                },
            ],
        )
        fan_in(state)
        commit_msg = mock_commit.call_args[0][1]
        assert "1.1" in commit_msg
        assert "1.2" in commit_msg
        assert "1.3" not in commit_msg

    @patch("langgraph_pipeline.executor.nodes.parallel._load_plan_yaml")
    @patch("langgraph_pipeline.executor.nodes.parallel.git_commit_files")
    def test_handles_empty_task_results(self, mock_commit, mock_load):
        mock_load.return_value = {}
        state = _make_state(plan_path="plan.yaml", task_results=[])
        result = fan_in(state)
        assert "plan_data" in result
        mock_commit.assert_not_called()
