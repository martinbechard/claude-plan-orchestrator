# tests/langgraph/pipeline/nodes/test_cost_accumulation.py
# End-to-end test verifying session_cost_usd accumulates across all pipeline nodes (D3).
# Design: docs/plans/2026-03-30-79-worker-cost-zero-despite-work-design.md

"""AC9: session_cost_usd must equal the sum of all stage costs by pipeline end.

Verifies that intake_analyze, structure_requirements, create_plan, and execute_plan
each add their costs to the running session_cost_usd rather than resetting it.
The test simulates LangGraph's state-threading by manually merging each node's
return dict into the running state before calling the next node.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from langgraph_pipeline.pipeline.nodes.execute_plan import execute_plan
from langgraph_pipeline.pipeline.nodes.intake import intake_analyze
from langgraph_pipeline.pipeline.nodes.plan_creation import create_plan
from langgraph_pipeline.pipeline.nodes.requirements import structure_requirements


# ─── Stage cost constants ─────────────────────────────────────────────────────

INTAKE_COST = 0.12
REQUIREMENTS_COST = 0.35
PLAN_COST = 0.48
EXECUTOR_COST = 1.25

EXPECTED_TOTAL_COST = INTAKE_COST + REQUIREMENTS_COST + PLAN_COST + EXECUTOR_COST

ITEM_SLUG = "test-cost-e2e"


# ─── State helpers ────────────────────────────────────────────────────────────


def _make_initial_state(item_path: str) -> dict:
    """Build a minimal PipelineState for a feature item starting at zero cost."""
    return {
        "item_path": item_path,
        "item_slug": ITEM_SLUG,
        "item_type": "feature",
        "item_name": "Test Cost End-to-End",
        "plan_path": None,
        "requirements_path": None,
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


def _merge(state: dict, updates: dict) -> dict:
    """Apply node return updates into state (simulates LangGraph state merge)."""
    merged = dict(state)
    merged.update(updates)
    return merged


# ─── Pipeline runner ──────────────────────────────────────────────────────────


def _run_pipeline_stages(tmp_path: Path) -> tuple[float, float, float, float]:
    """Run all four pipeline nodes with mocked LLM calls.

    Returns session_cost_usd captured after each stage:
    (after_intake, after_requirements, after_plan_creation, after_execute_plan)
    """
    item_file = tmp_path / "feature.md"
    item_file.write_text("Feature request for end-to-end cost accumulation testing.")

    plans_dir = tmp_path / "plans"
    plans_dir.mkdir()
    plan_file = plans_dir / f"{ITEM_SLUG}.yaml"
    plan_file.write_text("meta:\n  source_item: test\nsections: []\n")

    reqs_dir = tmp_path / "reqs"
    reqs_dir.mkdir()

    state = _make_initial_state(str(item_file))

    mock_executor_final_state = {
        "plan_cost_usd": EXECUTOR_COST,
        "plan_input_tokens": 1000,
        "plan_output_tokens": 500,
        "task_results": [],
        "current_task_id": None,
        "consecutive_failures": 0,
        "deadlock_detected": False,
        "deadlock_details": None,
    }
    mock_compiled = MagicMock()
    mock_compiled.invoke.return_value = mock_executor_final_state
    mock_executor_graph = MagicMock()
    mock_executor_graph.compile.return_value = mock_compiled

    with (
        # ── intake_analyze ──────────────────────────────────────────────────
        patch(
            "langgraph_pipeline.pipeline.nodes.intake._run_intake_analysis",
            return_value=("", "", INTAKE_COST, False),
        ),
        patch(
            "langgraph_pipeline.pipeline.nodes.intake._check_throttle",
            return_value=False,
        ),
        patch(
            "langgraph_pipeline.pipeline.nodes.intake._check_rag_dedup",
            return_value=False,
        ),
        patch("langgraph_pipeline.pipeline.nodes.intake._record_intake"),
        patch("langgraph_pipeline.pipeline.nodes.intake.add_trace_metadata"),
        # ── structure_requirements ──────────────────────────────────────────
        patch(
            "langgraph_pipeline.pipeline.nodes.requirements._call_llm",
            side_effect=[
                (
                    "### P1: Test requirement\n"
                    "Type: functional\nPriority: high\n"
                    "Description: Test cost accumulation.\n"
                    "Acceptance Criteria:\n- Works? YES = pass, NO = fail",
                    REQUIREMENTS_COST,
                    "",
                ),
                ("ACCEPT", 0.0, ""),
            ],
        ),
        patch(
            "langgraph_pipeline.pipeline.nodes.requirements.REQUIREMENTS_DIR",
            str(reqs_dir),
        ),
        patch("langgraph_pipeline.pipeline.nodes.requirements.add_trace_metadata"),
        # ── create_plan ─────────────────────────────────────────────────────
        patch(
            "langgraph_pipeline.pipeline.nodes.plan_creation.load_orchestrator_config",
            return_value={"agents_dir": str(tmp_path / "agents")},
        ),
        patch(
            "langgraph_pipeline.pipeline.nodes.plan_creation._build_planner_command",
            return_value=["echo", "{}"],
        ),
        patch(
            "langgraph_pipeline.pipeline.nodes.plan_creation._run_subprocess",
            return_value=(0, json.dumps({"total_cost_usd": PLAN_COST}), ""),
        ),
        patch(
            "langgraph_pipeline.pipeline.nodes.plan_creation._plan_exists",
            return_value=True,
        ),
        patch(
            "langgraph_pipeline.pipeline.nodes.plan_creation."
            "_ensure_acceptance_criteria_in_design"
        ),
        patch("langgraph_pipeline.pipeline.nodes.plan_creation.add_trace_metadata"),
        patch("langgraph_pipeline.pipeline.nodes.plan_creation.PLANS_DIR", str(plans_dir)),
        patch("langgraph_pipeline.pipeline.nodes.intake._save_subprocess_output"),
        patch("langgraph_pipeline.shared.claude_cli._report_worker_stats"),
        # ── execute_plan ────────────────────────────────────────────────────
        patch(
            "langgraph_pipeline.pipeline.nodes.execute_plan.build_executor_graph",
            return_value=mock_executor_graph,
        ),
        patch("langgraph_pipeline.pipeline.nodes.execute_plan.add_trace_metadata"),
    ):
        # Stage 1: intake
        intake_updates = intake_analyze(state)
        state = _merge(state, intake_updates)
        cost_after_intake = state["session_cost_usd"]

        # Stage 2: requirements
        req_updates = structure_requirements(state)
        state = _merge(state, req_updates)
        cost_after_requirements = state["session_cost_usd"]

        # Stage 3: plan creation
        plan_updates = create_plan(state)
        state = _merge(state, plan_updates)
        cost_after_plan = state["session_cost_usd"]

        # Stage 4: execute plan
        exec_updates = execute_plan(state)
        state = _merge(state, exec_updates)
        cost_after_exec = state["session_cost_usd"]

    return cost_after_intake, cost_after_requirements, cost_after_plan, cost_after_exec


# ─── Tests ────────────────────────────────────────────────────────────────────


class TestEndToEndCostAccumulation:
    """AC9: verify session_cost_usd accumulates correctly through all stages."""

    def test_final_cost_equals_sum_of_all_stages(self, tmp_path):
        _, _, _, cost_after_exec = _run_pipeline_stages(tmp_path)
        assert cost_after_exec == pytest.approx(EXPECTED_TOTAL_COST)

    def test_cost_is_monotonically_non_decreasing(self, tmp_path):
        cost_after_intake, cost_after_req, cost_after_plan, cost_after_exec = (
            _run_pipeline_stages(tmp_path)
        )
        assert cost_after_req >= cost_after_intake
        assert cost_after_plan >= cost_after_req
        assert cost_after_exec >= cost_after_plan

    def test_intake_stage_contributes_expected_cost(self, tmp_path):
        cost_after_intake, _, _, _ = _run_pipeline_stages(tmp_path)
        assert cost_after_intake == pytest.approx(INTAKE_COST)

    def test_requirements_stage_adds_to_intake_cost(self, tmp_path):
        cost_after_intake, cost_after_req, _, _ = _run_pipeline_stages(tmp_path)
        requirements_delta = cost_after_req - cost_after_intake
        assert requirements_delta == pytest.approx(REQUIREMENTS_COST)

    def test_plan_creation_stage_adds_to_prior_cost(self, tmp_path):
        _, cost_after_req, cost_after_plan, _ = _run_pipeline_stages(tmp_path)
        plan_delta = cost_after_plan - cost_after_req
        assert plan_delta == pytest.approx(PLAN_COST)

    def test_executor_stage_adds_to_prior_cost(self, tmp_path):
        _, _, cost_after_plan, cost_after_exec = _run_pipeline_stages(tmp_path)
        executor_delta = cost_after_exec - cost_after_plan
        assert executor_delta == pytest.approx(EXECUTOR_COST)

    def test_cost_never_resets_to_zero_between_stages(self, tmp_path):
        costs = _run_pipeline_stages(tmp_path)
        assert all(c > 0.0 for c in costs), (
            "session_cost_usd was reset to zero between pipeline stages"
        )
