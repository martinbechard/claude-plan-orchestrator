# tests/langgraph/pipeline/nodes/test_execute_plan.py
# Unit tests for the execute_plan node.
# Design: docs/plans/2026-02-26-05-task-execution-subgraph-design.md

"""Tests for langgraph_pipeline.pipeline.nodes.execute_plan.

The execute_plan node invokes the executor subgraph to run a YAML plan.
These tests verify state mapping, the no-plan-path guard, and that cost
and token totals are passed through from the subgraph's final state.
"""

import textwrap
from unittest.mock import MagicMock, call, patch

import pytest

from langgraph_pipeline.pipeline.nodes.execute_plan import (
    _INITIAL_COST,
    _INITIAL_FAILURES,
    _INITIAL_TASK_ATTEMPT,
    _INITIAL_TOKENS,
    _TERMINAL_STATUSES,
    _plan_task_snapshot,
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
        "plan_path": "tmp/plans/01-bug.yaml",
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


def _make_mock_subgraph(
    cost_usd: float = 0.0,
    input_tokens: int = 0,
    output_tokens: int = 0,
    task_results: list | None = None,
    deadlock_detected: bool = False,
    deadlock_details: list | None = None,
):
    """Return a mock compiled executor subgraph.

    The mock's invoke() method returns a fake final TaskState dict.
    """
    final_state = {
        "plan_cost_usd": cost_usd,
        "plan_input_tokens": input_tokens,
        "plan_output_tokens": output_tokens,
        "task_results": task_results or [],
        "current_task_id": None,
        "consecutive_failures": 0,
        "deadlock_detected": deadlock_detected,
        "deadlock_details": deadlock_details,
    }
    compiled = MagicMock()
    compiled.invoke.return_value = final_state
    return compiled


# ─── Tests: no plan_path guard ────────────────────────────────────────────────


class TestExecutePlanNoPlanPath:
    def test_returns_execution_failed_when_plan_path_is_none(self):
        state = _make_state(plan_path=None)
        result = execute_plan(state)
        assert result == {"execution_failed": True}

    def test_does_not_invoke_subgraph_when_no_plan_path(self):
        state = _make_state(plan_path=None)
        with patch(
            "langgraph_pipeline.pipeline.nodes.execute_plan.build_executor_graph"
        ) as mock_build:
            execute_plan(state)
        mock_build.assert_not_called()


# ─── Tests: subgraph invocation ───────────────────────────────────────────────


class TestExecutePlanSubgraphInvocation:
    def test_invokes_subgraph_with_plan_path(self):
        state = _make_state(plan_path="tmp/plans/test-plan.yaml")

        mock_compiled = _make_mock_subgraph()
        with patch(
            "langgraph_pipeline.pipeline.nodes.execute_plan.build_executor_graph"
        ) as mock_build:
            mock_build.return_value.compile.return_value = mock_compiled
            execute_plan(state)

        mock_compiled.invoke.assert_called_once()
        invocation_args = mock_compiled.invoke.call_args[0][0]
        assert invocation_args["plan_path"] == "tmp/plans/test-plan.yaml"

    def test_initial_task_state_has_zero_accumulators(self):
        state = _make_state(plan_path="tmp/plans/test-plan.yaml")

        captured_state = {}
        mock_compiled = MagicMock()
        mock_compiled.invoke.side_effect = lambda s, config=None: (
            captured_state.update(s)
            or {
                "plan_cost_usd": 0.0,
                "plan_input_tokens": 0,
                "plan_output_tokens": 0,
                "task_results": [],
            }
        )
        with patch(
            "langgraph_pipeline.pipeline.nodes.execute_plan.build_executor_graph"
        ) as mock_build:
            mock_build.return_value.compile.return_value = mock_compiled
            execute_plan(state)

        assert captured_state["plan_cost_usd"] == _INITIAL_COST
        assert captured_state["plan_input_tokens"] == _INITIAL_TOKENS
        assert captured_state["plan_output_tokens"] == _INITIAL_TOKENS
        assert captured_state["task_attempt"] == _INITIAL_TASK_ATTEMPT
        assert captured_state["consecutive_failures"] == _INITIAL_FAILURES


# ─── Tests: cost and token mapping ────────────────────────────────────────────


class TestExecutePlanCostMapping:
    def test_maps_plan_cost_to_session_cost(self):
        state = _make_state(plan_path="tmp/plans/plan.yaml")
        mock_compiled = _make_mock_subgraph(cost_usd=1.23)
        with patch(
            "langgraph_pipeline.pipeline.nodes.execute_plan.build_executor_graph"
        ) as mock_build:
            mock_build.return_value.compile.return_value = mock_compiled
            result = execute_plan(state)

        assert result["session_cost_usd"] == pytest.approx(1.23)

    def test_maps_plan_tokens_to_session_tokens(self):
        state = _make_state(plan_path="tmp/plans/plan.yaml")
        mock_compiled = _make_mock_subgraph(input_tokens=5000, output_tokens=2000)
        with patch(
            "langgraph_pipeline.pipeline.nodes.execute_plan.build_executor_graph"
        ) as mock_build:
            mock_build.return_value.compile.return_value = mock_compiled
            result = execute_plan(state)

        assert result["session_input_tokens"] == 5000
        assert result["session_output_tokens"] == 2000

    def test_returns_zeros_when_subgraph_returns_none_accumulators(self):
        state = _make_state(plan_path="tmp/plans/plan.yaml")
        mock_compiled = MagicMock()
        mock_compiled.invoke.return_value = {
            "plan_cost_usd": None,
            "plan_input_tokens": None,
            "plan_output_tokens": None,
            "task_results": [],
        }
        with patch(
            "langgraph_pipeline.pipeline.nodes.execute_plan.build_executor_graph"
        ) as mock_build:
            mock_build.return_value.compile.return_value = mock_compiled
            result = execute_plan(state)

        assert result["session_cost_usd"] == 0.0
        assert result["session_input_tokens"] == 0
        assert result["session_output_tokens"] == 0

    def test_returns_all_three_session_fields(self):
        state = _make_state(plan_path="tmp/plans/plan.yaml")
        mock_compiled = _make_mock_subgraph(cost_usd=0.05, input_tokens=100, output_tokens=50)
        with patch(
            "langgraph_pipeline.pipeline.nodes.execute_plan.build_executor_graph"
        ) as mock_build:
            mock_build.return_value.compile.return_value = mock_compiled
            result = execute_plan(state)

        assert "session_cost_usd" in result
        assert "session_input_tokens" in result
        assert "session_output_tokens" in result


# ─── Tests: additive accumulation from prior state ────────────────────────────


class TestExecutePlanAdditiveAccumulation:
    """execute_plan must add executor costs to prior pipeline state costs (D2)."""

    def test_adds_executor_cost_to_prior_session_cost(self):
        state = _make_state(
            plan_path="tmp/plans/plan.yaml",
            session_cost_usd=2.50,
        )
        mock_compiled = _make_mock_subgraph(cost_usd=1.23)
        with patch(
            "langgraph_pipeline.pipeline.nodes.execute_plan.build_executor_graph"
        ) as mock_build:
            mock_build.return_value.compile.return_value = mock_compiled
            result = execute_plan(state)

        assert result["session_cost_usd"] == pytest.approx(3.73)

    def test_adds_executor_tokens_to_prior_session_tokens(self):
        state = _make_state(
            plan_path="tmp/plans/plan.yaml",
            session_input_tokens=3000,
            session_output_tokens=1500,
        )
        mock_compiled = _make_mock_subgraph(input_tokens=5000, output_tokens=2000)
        with patch(
            "langgraph_pipeline.pipeline.nodes.execute_plan.build_executor_graph"
        ) as mock_build:
            mock_build.return_value.compile.return_value = mock_compiled
            result = execute_plan(state)

        assert result["session_input_tokens"] == 8000
        assert result["session_output_tokens"] == 3500

    def test_result_is_zero_when_both_prior_and_executor_are_zero(self):
        state = _make_state(
            plan_path="tmp/plans/plan.yaml",
            session_cost_usd=0.0,
        )
        mock_compiled = _make_mock_subgraph(cost_usd=0.0)
        with patch(
            "langgraph_pipeline.pipeline.nodes.execute_plan.build_executor_graph"
        ) as mock_build:
            mock_build.return_value.compile.return_value = mock_compiled
            result = execute_plan(state)

        assert result["session_cost_usd"] == pytest.approx(0.0)

    def test_prior_cost_preserved_when_executor_returns_zero(self):
        state = _make_state(
            plan_path="tmp/plans/plan.yaml",
            session_cost_usd=1.75,
        )
        mock_compiled = _make_mock_subgraph(cost_usd=0.0)
        with patch(
            "langgraph_pipeline.pipeline.nodes.execute_plan.build_executor_graph"
        ) as mock_build:
            mock_build.return_value.compile.return_value = mock_compiled
            result = execute_plan(state)

        assert result["session_cost_usd"] == pytest.approx(1.75)

    def test_cost_never_decreases_after_executor(self):
        prior = 5.00
        state = _make_state(
            plan_path="tmp/plans/plan.yaml",
            session_cost_usd=prior,
        )
        mock_compiled = _make_mock_subgraph(cost_usd=0.50)
        with patch(
            "langgraph_pipeline.pipeline.nodes.execute_plan.build_executor_graph"
        ) as mock_build:
            mock_build.return_value.compile.return_value = mock_compiled
            result = execute_plan(state)

        assert result["session_cost_usd"] >= prior


# ─── Tests: _plan_task_snapshot helper ────────────────────────────────────────


_SAMPLE_PLAN_YAML = textwrap.dedent("""\
    sections:
    - id: '1'
      name: Section One
      tasks:
      - id: '1.1'
        name: Task A
        status: verified
      - id: '1.2'
        name: Task B
        status: pending
    - id: '2'
      name: Section Two
      tasks:
      - id: '2.1'
        name: Task C
        status: skipped
      - id: '2.2'
        name: Task D
        status: failed
""")


class TestPlanTaskSnapshot:
    def test_extracts_all_tasks_from_all_sections(self, tmp_path):
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(_SAMPLE_PLAN_YAML)
        result = _plan_task_snapshot(str(plan_file))
        assert result["total_count"] == 4
        ids = [t["task_id"] for t in result["plan_tasks"]]
        assert ids == ["1.1", "1.2", "2.1", "2.2"]

    def test_extracts_statuses_correctly(self, tmp_path):
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(_SAMPLE_PLAN_YAML)
        result = _plan_task_snapshot(str(plan_file))
        statuses = {t["task_id"]: t["status"] for t in result["plan_tasks"]}
        assert statuses["1.1"] == "verified"
        assert statuses["1.2"] == "pending"
        assert statuses["2.1"] == "skipped"
        assert statuses["2.2"] == "failed"

    def test_counts_terminal_statuses_as_completed(self, tmp_path):
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(_SAMPLE_PLAN_YAML)
        result = _plan_task_snapshot(str(plan_file))
        # verified, skipped, failed are all terminal → 3 terminal out of 4
        assert result["completed_count"] == 3
        assert result["total_count"] == 4

    def test_returns_empty_snapshot_on_missing_file(self):
        result = _plan_task_snapshot("/nonexistent/path/plan.yaml")
        assert result == {"plan_tasks": [], "completed_count": 0, "total_count": 0}

    def test_returns_empty_snapshot_on_invalid_yaml(self, tmp_path):
        plan_file = tmp_path / "bad.yaml"
        plan_file.write_text(":: invalid: yaml: [unclosed")
        result = _plan_task_snapshot(str(plan_file))
        assert result == {"plan_tasks": [], "completed_count": 0, "total_count": 0}

    def test_returns_empty_snapshot_for_plan_with_no_sections(self, tmp_path):
        plan_file = tmp_path / "empty.yaml"
        plan_file.write_text("meta:\n  source_item: foo.md\n")
        result = _plan_task_snapshot(str(plan_file))
        assert result == {"plan_tasks": [], "completed_count": 0, "total_count": 0}

    def test_verified_counted_as_terminal(self, tmp_path):
        """The 'verified' status is recognized as terminal in snapshot counting."""
        plan_yaml = textwrap.dedent("""\
            sections:
            - id: '1'
              tasks:
              - id: '1.1'
                status: verified
              - id: '1.2'
                status: pending
        """)
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(plan_yaml)
        result = _plan_task_snapshot(str(plan_file))
        assert result["completed_count"] == 1
        assert result["total_count"] == 2

    def test_completed_still_counted_as_terminal(self, tmp_path):
        """Legacy 'completed' status is still terminal for snapshot counting."""
        plan_yaml = textwrap.dedent("""\
            sections:
            - id: '1'
              tasks:
              - id: '1.1'
                status: completed
              - id: '1.2'
                status: pending
        """)
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(plan_yaml)
        result = _plan_task_snapshot(str(plan_file))
        assert result["completed_count"] == 1
        assert result["total_count"] == 2


class TestTerminalStatuses:
    """_TERMINAL_STATUSES includes verified alongside legacy terminal statuses."""

    def test_verified_is_terminal(self):
        assert "verified" in _TERMINAL_STATUSES

    def test_completed_is_terminal(self):
        assert "completed" in _TERMINAL_STATUSES

    def test_failed_is_terminal(self):
        assert "failed" in _TERMINAL_STATUSES

    def test_skipped_is_terminal(self):
        assert "skipped" in _TERMINAL_STATUSES

    def test_pending_is_not_terminal(self):
        assert "pending" not in _TERMINAL_STATUSES

    def test_in_progress_is_not_terminal(self):
        assert "in_progress" not in _TERMINAL_STATUSES


# ─── Tests: plan task snapshot trace metadata ──────────────────────────────────


class TestExecutePlanTaskSnapshot:
    def _run_with_plan(self, tmp_path, plan_yaml: str):
        """Write a plan YAML, run execute_plan, return captured add_trace_metadata calls."""
        plan_file = tmp_path / "plan.yaml"
        plan_file.write_text(plan_yaml)
        state = _make_state(plan_path=str(plan_file))

        mock_compiled = _make_mock_subgraph()
        captured_calls: list[dict] = []

        def fake_add_trace(metadata: dict) -> None:
            captured_calls.append(metadata)

        with (
            patch(
                "langgraph_pipeline.pipeline.nodes.execute_plan.build_executor_graph"
            ) as mock_build,
            patch(
                "langgraph_pipeline.pipeline.nodes.execute_plan.add_trace_metadata",
                side_effect=fake_add_trace,
            ),
        ):
            mock_build.return_value.compile.return_value = mock_compiled
            execute_plan(state)

        return captured_calls

    def test_emits_start_checkpoint_trace(self, tmp_path):
        calls = self._run_with_plan(tmp_path, _SAMPLE_PLAN_YAML)
        start_calls = [c for c in calls if c.get("checkpoint") == "start"]
        assert len(start_calls) == 1

    def test_emits_end_checkpoint_trace(self, tmp_path):
        calls = self._run_with_plan(tmp_path, _SAMPLE_PLAN_YAML)
        end_calls = [c for c in calls if c.get("checkpoint") == "end"]
        assert len(end_calls) == 1

    def test_start_trace_contains_plan_tasks(self, tmp_path):
        calls = self._run_with_plan(tmp_path, _SAMPLE_PLAN_YAML)
        start = next(c for c in calls if c.get("checkpoint") == "start")
        assert "plan_tasks" in start
        assert len(start["plan_tasks"]) == 4

    def test_start_trace_contains_counts(self, tmp_path):
        calls = self._run_with_plan(tmp_path, _SAMPLE_PLAN_YAML)
        start = next(c for c in calls if c.get("checkpoint") == "start")
        assert start["total_count"] == 4
        assert start["completed_count"] == 3

    def test_end_trace_contains_plan_tasks(self, tmp_path):
        calls = self._run_with_plan(tmp_path, _SAMPLE_PLAN_YAML)
        end = next(c for c in calls if c.get("checkpoint") == "end")
        assert "plan_tasks" in end
        assert len(end["plan_tasks"]) == 4

    def test_end_trace_contains_counts(self, tmp_path):
        calls = self._run_with_plan(tmp_path, _SAMPLE_PLAN_YAML)
        end = next(c for c in calls if c.get("checkpoint") == "end")
        assert end["total_count"] == 4
        assert end["completed_count"] == 3

    def test_plan_tasks_have_task_id_and_status_fields(self, tmp_path):
        calls = self._run_with_plan(tmp_path, _SAMPLE_PLAN_YAML)
        start = next(c for c in calls if c.get("checkpoint") == "start")
        for task in start["plan_tasks"]:
            assert "task_id" in task
            assert "status" in task

    def test_start_trace_emitted_before_end_trace(self, tmp_path):
        calls = self._run_with_plan(tmp_path, _SAMPLE_PLAN_YAML)
        checkpoints = [c.get("checkpoint") for c in calls if c.get("checkpoint")]
        assert checkpoints.index("start") < checkpoints.index("end")

    def test_no_trace_emitted_when_no_plan_path(self):
        state = _make_state(plan_path=None)
        with patch(
            "langgraph_pipeline.pipeline.nodes.execute_plan.add_trace_metadata"
        ) as mock_trace:
            execute_plan(state)
        mock_trace.assert_not_called()


# ─── Tests: deadlock signal propagation ───────────────────────────────────────


class TestExecutePlanDeadlockPropagation:
    """execute_plan propagates deadlock signal from TaskState to PipelineState."""

    def test_executor_deadlock_true_when_deadlock_detected(self):
        state = _make_state(plan_path="tmp/plans/plan.yaml")
        mock_compiled = _make_mock_subgraph(deadlock_detected=True)
        with patch(
            "langgraph_pipeline.pipeline.nodes.execute_plan.build_executor_graph"
        ) as mock_build:
            mock_build.return_value.compile.return_value = mock_compiled
            result = execute_plan(state)

        assert result["executor_deadlock"] is True

    def test_executor_deadlock_false_when_no_deadlock(self):
        state = _make_state(plan_path="tmp/plans/plan.yaml")
        mock_compiled = _make_mock_subgraph(deadlock_detected=False)
        with patch(
            "langgraph_pipeline.pipeline.nodes.execute_plan.build_executor_graph"
        ) as mock_build:
            mock_build.return_value.compile.return_value = mock_compiled
            result = execute_plan(state)

        assert result["executor_deadlock"] is False

    def test_executor_deadlock_false_when_field_absent(self):
        state = _make_state(plan_path="tmp/plans/plan.yaml")
        mock_compiled = MagicMock()
        mock_compiled.invoke.return_value = {
            "plan_cost_usd": 0.0,
            "plan_input_tokens": 0,
            "plan_output_tokens": 0,
            "task_results": [],
        }
        with patch(
            "langgraph_pipeline.pipeline.nodes.execute_plan.build_executor_graph"
        ) as mock_build:
            mock_build.return_value.compile.return_value = mock_compiled
            result = execute_plan(state)

        assert result["executor_deadlock"] is False

    def test_executor_deadlock_details_propagated(self):
        details = [
            {"task_id": "0.4", "task_name": "Task Four", "unsatisfied_deps": ["0.3"]},
            {"task_id": "0.5", "task_name": "Task Five", "unsatisfied_deps": ["0.3", "0.4"]},
        ]
        state = _make_state(plan_path="tmp/plans/plan.yaml")
        mock_compiled = _make_mock_subgraph(deadlock_detected=True, deadlock_details=details)
        with patch(
            "langgraph_pipeline.pipeline.nodes.execute_plan.build_executor_graph"
        ) as mock_build:
            mock_build.return_value.compile.return_value = mock_compiled
            result = execute_plan(state)

        assert result["executor_deadlock_details"] == details

    def test_executor_deadlock_details_none_when_no_deadlock(self):
        state = _make_state(plan_path="tmp/plans/plan.yaml")
        mock_compiled = _make_mock_subgraph(deadlock_detected=False, deadlock_details=None)
        with patch(
            "langgraph_pipeline.pipeline.nodes.execute_plan.build_executor_graph"
        ) as mock_build:
            mock_build.return_value.compile.return_value = mock_compiled
            result = execute_plan(state)

        assert result["executor_deadlock_details"] is None

    def test_executor_deadlock_field_present_in_result(self):
        state = _make_state(plan_path="tmp/plans/plan.yaml")
        mock_compiled = _make_mock_subgraph()
        with patch(
            "langgraph_pipeline.pipeline.nodes.execute_plan.build_executor_graph"
        ) as mock_build:
            mock_build.return_value.compile.return_value = mock_compiled
            result = execute_plan(state)

        assert "executor_deadlock" in result
        assert "executor_deadlock_details" in result
