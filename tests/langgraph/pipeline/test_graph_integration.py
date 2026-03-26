# tests/langgraph/pipeline/test_graph_integration.py
# Integration tests for the full pipeline StateGraph.
# Design: docs/plans/2026-02-26-04-pipeline-graph-nodes-design.md

"""Integration tests for langgraph_pipeline.pipeline.graph.

These tests build and invoke the full compiled StateGraph with all node
functions mocked, verifying that conditional edges route correctly for the
two key scenarios: feature item and defect item.

The CLI pre-scans items before invoking the graph, so all tests start with
item_path pre-populated in the initial state — matching the real invocation
pattern.

Patching is applied at the graph module's namespace (e.g.,
langgraph_pipeline.pipeline.graph.intake_analyze) because that is where the
name bindings live when build_graph() calls add_node().
"""

from unittest.mock import patch

import pytest

from langgraph_pipeline.pipeline.graph import (
    PIPELINE_THREAD_ID,
    build_graph,
)

# ─── Constants ────────────────────────────────────────────────────────────────

GRAPH_MODULE = "langgraph_pipeline.pipeline.graph"
TEST_THREAD_PREFIX = "test-integration-"

FEATURE_ITEM_PATH = "docs/feature-backlog/01-test-feature.md"
DEFECT_ITEM_PATH = "docs/defect-backlog/01-test-defect.md"

PASS_VERIFICATION_RECORD = {
    "outcome": "PASS",
    "timestamp": "2026-01-01T00:00:00Z",
    "notes": "Symptom resolved.",
}

FAIL_VERIFICATION_RECORD = {
    "outcome": "FAIL",
    "timestamp": "2026-01-01T00:00:00Z",
    "notes": "Symptom still reproducible.",
}

# ─── Helpers ──────────────────────────────────────────────────────────────────


def _feature_initial_state() -> dict:
    """Return a minimal valid PipelineState dict for a feature item graph invocation.

    item_path is pre-populated to match the CLI's pre-scan behaviour.
    """
    return {
        "item_path": FEATURE_ITEM_PATH,
        "item_slug": "01-test-feature",
        "item_type": "feature",
        "item_name": "01 Test Feature",
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


def _defect_initial_state() -> dict:
    """Return a minimal valid PipelineState dict for a defect item graph invocation.

    item_path is pre-populated to match the CLI's pre-scan behaviour.
    """
    return {
        "item_path": DEFECT_ITEM_PATH,
        "item_slug": "01-test-defect",
        "item_type": "defect",
        "item_name": "01 Test Defect",
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


def _config(suffix: str) -> dict:
    """Build a LangGraph config dict with a unique thread_id."""
    return {"configurable": {"thread_id": f"{TEST_THREAD_PREFIX}{suffix}"}}


# ─── Tests ────────────────────────────────────────────────────────────────────


class TestFeatureItem:
    """Feature items skip verify_symptoms and go directly to archive."""

    def test_feature_routes_through_archive(self, checkpointer):
        """A feature item traverses: intake → create_plan → execute → archive."""
        node_calls: list[str] = []

        def mock_intake(state: dict) -> dict:
            node_calls.append("intake_analyze")
            return {}

        def mock_create_plan(state: dict) -> dict:
            node_calls.append("create_plan")
            return {"plan_path": ".claude/plans/01-test-feature.yaml"}

        def mock_execute_plan(state: dict) -> dict:
            node_calls.append("execute_plan")
            return {}

        def mock_archive(state: dict) -> dict:
            node_calls.append("archive")
            return {}

        with (
            patch(f"{GRAPH_MODULE}.intake_analyze", mock_intake),
            patch(f"{GRAPH_MODULE}.create_plan", mock_create_plan),
            patch(f"{GRAPH_MODULE}.execute_plan", mock_execute_plan),
            patch(f"{GRAPH_MODULE}.archive", mock_archive),
        ):
            compiled = build_graph().compile(checkpointer=checkpointer)
            result = compiled.invoke(_feature_initial_state(), config=_config("feature"))

        assert node_calls == [
            "intake_analyze",
            "create_plan",
            "execute_plan",
            "archive",
        ]
        assert result["item_type"] == "feature"

    def test_verify_symptoms_not_called_for_feature(self, checkpointer):
        """verify_symptoms is never called when item_type is 'feature'."""
        verify_called = False

        def mock_intake(state: dict) -> dict:
            return {}

        def mock_create_plan(state: dict) -> dict:
            return {"plan_path": ".claude/plans/01-test-feature.yaml"}

        def mock_execute_plan(state: dict) -> dict:
            return {}

        def mock_verify(state: dict) -> dict:
            nonlocal verify_called
            verify_called = True
            return {}

        def mock_archive(state: dict) -> dict:
            return {}

        with (
            patch(f"{GRAPH_MODULE}.intake_analyze", mock_intake),
            patch(f"{GRAPH_MODULE}.create_plan", mock_create_plan),
            patch(f"{GRAPH_MODULE}.execute_plan", mock_execute_plan),
            patch(f"{GRAPH_MODULE}.verify_symptoms", mock_verify),
            patch(f"{GRAPH_MODULE}.archive", mock_archive),
        ):
            compiled = build_graph().compile(checkpointer=checkpointer)
            compiled.invoke(_feature_initial_state(), config=_config("feature-no-verify"))

        assert not verify_called


class TestDefectItemPassVerification:
    """Defect items that PASS verification route to archive after verify_symptoms."""

    def test_defect_routes_through_verification_to_archive(self, checkpointer):
        """A defect that PASSes routes: intake → create_plan → execute → verify → archive."""
        node_calls: list[str] = []

        def mock_intake(state: dict) -> dict:
            node_calls.append("intake_analyze")
            return {}

        def mock_create_plan(state: dict) -> dict:
            node_calls.append("create_plan")
            return {"plan_path": ".claude/plans/01-test-defect.yaml"}

        def mock_execute_plan(state: dict) -> dict:
            node_calls.append("execute_plan")
            return {}

        def mock_verify(state: dict) -> dict:
            node_calls.append("verify_symptoms")
            cycle = (state.get("verification_cycle") or 0) + 1
            return {
                "verification_cycle": cycle,
                "verification_history": [PASS_VERIFICATION_RECORD],
            }

        def mock_archive(state: dict) -> dict:
            node_calls.append("archive")
            return {}

        with (
            patch(f"{GRAPH_MODULE}.intake_analyze", mock_intake),
            patch(f"{GRAPH_MODULE}.create_plan", mock_create_plan),
            patch(f"{GRAPH_MODULE}.execute_plan", mock_execute_plan),
            patch(f"{GRAPH_MODULE}.verify_symptoms", mock_verify),
            patch(f"{GRAPH_MODULE}.archive", mock_archive),
        ):
            compiled = build_graph().compile(checkpointer=checkpointer)
            result = compiled.invoke(_defect_initial_state(), config=_config("defect-pass"))

        assert node_calls == [
            "intake_analyze",
            "create_plan",
            "execute_plan",
            "verify_symptoms",
            "archive",
        ]
        assert result["verification_history"][-1]["outcome"] == "PASS"


class TestDefectItemFailRetry:
    """Defect items that FAIL verification and still have cycles left retry create_plan."""

    def test_defect_fail_retries_create_plan_then_archives(self, checkpointer):
        """FAIL on cycle 1 retries create_plan; PASS on cycle 2 archives."""
        node_calls: list[str] = []
        verify_call_count = 0

        def mock_intake(state: dict) -> dict:
            node_calls.append("intake_analyze")
            return {}

        def mock_create_plan(state: dict) -> dict:
            node_calls.append("create_plan")
            return {"plan_path": ".claude/plans/01-test-defect.yaml"}

        def mock_execute_plan(state: dict) -> dict:
            node_calls.append("execute_plan")
            return {}

        def mock_verify(state: dict) -> dict:
            nonlocal verify_call_count
            node_calls.append("verify_symptoms")
            verify_call_count += 1
            cycle = (state.get("verification_cycle") or 0) + 1
            # First call FAILs, second call PASSes.
            outcome_record = (
                FAIL_VERIFICATION_RECORD if verify_call_count == 1 else PASS_VERIFICATION_RECORD
            )
            return {
                "verification_cycle": cycle,
                "verification_history": [outcome_record],
            }

        def mock_archive(state: dict) -> dict:
            node_calls.append("archive")
            return {}

        with (
            patch(f"{GRAPH_MODULE}.intake_analyze", mock_intake),
            patch(f"{GRAPH_MODULE}.create_plan", mock_create_plan),
            patch(f"{GRAPH_MODULE}.execute_plan", mock_execute_plan),
            patch(f"{GRAPH_MODULE}.verify_symptoms", mock_verify),
            patch(f"{GRAPH_MODULE}.archive", mock_archive),
        ):
            compiled = build_graph().compile(checkpointer=checkpointer)
            result = compiled.invoke(_defect_initial_state(), config=_config("defect-fail-retry"))

        assert node_calls == [
            "intake_analyze",
            "create_plan",
            "execute_plan",
            "verify_symptoms",
            "create_plan",
            "execute_plan",
            "verify_symptoms",
            "archive",
        ]
        assert result["verification_history"][-1]["outcome"] == "PASS"


class TestGraphCompilation:
    """Smoke tests for graph structure and compilation."""

    def test_graph_compiles_with_checkpointer(self, checkpointer):
        """build_graph() should compile without errors when given a checkpointer."""
        compiled = build_graph().compile(checkpointer=checkpointer)
        assert compiled is not None

    def test_pipeline_thread_id_constant_is_set(self):
        """PIPELINE_THREAD_ID should be the canonical thread identifier string."""
        assert PIPELINE_THREAD_ID == "pipeline-main"
