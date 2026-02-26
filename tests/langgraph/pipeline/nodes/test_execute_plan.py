# tests/langgraph/pipeline/nodes/test_execute_plan.py
# Unit tests for the execute_plan node.
# Design: docs/plans/2026-02-26-05-task-execution-subgraph-design.md

"""Tests for langgraph_pipeline.pipeline.nodes.execute_plan.

The execute_plan node invokes the executor subgraph to run a YAML plan.
These tests verify state mapping, the no-plan-path guard, and that cost
and token totals are passed through from the subgraph's final state.
"""

from unittest.mock import MagicMock, patch

import pytest

from langgraph_pipeline.pipeline.nodes.execute_plan import (
    _INITIAL_COST,
    _INITIAL_FAILURES,
    _INITIAL_TASK_ATTEMPT,
    _INITIAL_TOKENS,
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


def _make_mock_subgraph(
    cost_usd: float = 0.0,
    input_tokens: int = 0,
    output_tokens: int = 0,
    task_results: list | None = None,
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
    }
    compiled = MagicMock()
    compiled.invoke.return_value = final_state
    return compiled


# ─── Tests: no plan_path guard ────────────────────────────────────────────────


class TestExecutePlanNoPlanPath:
    def test_returns_empty_dict_when_plan_path_is_none(self):
        state = _make_state(plan_path=None)
        result = execute_plan(state)
        assert result == {}

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
        state = _make_state(plan_path=".claude/plans/test-plan.yaml")

        mock_compiled = _make_mock_subgraph()
        with patch(
            "langgraph_pipeline.pipeline.nodes.execute_plan.build_executor_graph"
        ) as mock_build:
            mock_build.return_value.compile.return_value = mock_compiled
            execute_plan(state)

        mock_compiled.invoke.assert_called_once()
        invocation_args = mock_compiled.invoke.call_args[0][0]
        assert invocation_args["plan_path"] == ".claude/plans/test-plan.yaml"

    def test_initial_task_state_has_zero_accumulators(self):
        state = _make_state(plan_path=".claude/plans/test-plan.yaml")

        captured_state = {}
        mock_compiled = MagicMock()
        mock_compiled.invoke.side_effect = lambda s: (
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
        state = _make_state(plan_path=".claude/plans/plan.yaml")
        mock_compiled = _make_mock_subgraph(cost_usd=1.23)
        with patch(
            "langgraph_pipeline.pipeline.nodes.execute_plan.build_executor_graph"
        ) as mock_build:
            mock_build.return_value.compile.return_value = mock_compiled
            result = execute_plan(state)

        assert result["session_cost_usd"] == pytest.approx(1.23)

    def test_maps_plan_tokens_to_session_tokens(self):
        state = _make_state(plan_path=".claude/plans/plan.yaml")
        mock_compiled = _make_mock_subgraph(input_tokens=5000, output_tokens=2000)
        with patch(
            "langgraph_pipeline.pipeline.nodes.execute_plan.build_executor_graph"
        ) as mock_build:
            mock_build.return_value.compile.return_value = mock_compiled
            result = execute_plan(state)

        assert result["session_input_tokens"] == 5000
        assert result["session_output_tokens"] == 2000

    def test_returns_zeros_when_subgraph_returns_none_accumulators(self):
        state = _make_state(plan_path=".claude/plans/plan.yaml")
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
        state = _make_state(plan_path=".claude/plans/plan.yaml")
        mock_compiled = _make_mock_subgraph(cost_usd=0.05, input_tokens=100, output_tokens=50)
        with patch(
            "langgraph_pipeline.pipeline.nodes.execute_plan.build_executor_graph"
        ) as mock_build:
            mock_build.return_value.compile.return_value = mock_compiled
            result = execute_plan(state)

        assert "session_cost_usd" in result
        assert "session_input_tokens" in result
        assert "session_output_tokens" in result
