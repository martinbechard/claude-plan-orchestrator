# tests/langgraph/executor/test_escalation.py
# Unit tests for the model escalation module and escalate_node trace metadata.
# Design: docs/plans/2026-02-26-05-task-execution-subgraph-design.md

"""Tests for langgraph_pipeline.executor.escalation and _escalate_node in graph."""

from typing import get_type_hints
from unittest.mock import patch

from langgraph_pipeline.executor.escalation import (
    DEFAULT_STARTING_MODEL,
    MODEL_TIER_PROGRESSION,
    EscalationConfig,
    default_escalation_config,
    escalate_model,
    reset_model,
)


class TestModelTierProgression:
    """MODEL_TIER_PROGRESSION defines the correct ordered tier sequence."""

    def test_progression_starts_with_haiku(self):
        assert MODEL_TIER_PROGRESSION[0] == "haiku"

    def test_progression_ends_with_opus(self):
        assert MODEL_TIER_PROGRESSION[-1] == "opus"

    def test_sonnet_is_between_haiku_and_opus(self):
        haiku_idx = MODEL_TIER_PROGRESSION.index("haiku")
        sonnet_idx = MODEL_TIER_PROGRESSION.index("sonnet")
        opus_idx = MODEL_TIER_PROGRESSION.index("opus")
        assert haiku_idx < sonnet_idx < opus_idx

    def test_progression_has_three_tiers(self):
        assert len(MODEL_TIER_PROGRESSION) == 3


class TestDefaultStartingModel:
    """DEFAULT_STARTING_MODEL is haiku."""

    def test_default_is_haiku(self):
        assert DEFAULT_STARTING_MODEL == "haiku"


class TestEscalationConfig:
    """EscalationConfig TypedDict has the expected fields."""

    def test_required_keys_present(self):
        hints = get_type_hints(EscalationConfig)
        assert "enabled" in hints
        assert "starting_model" in hints

    def test_can_construct_enabled_config(self):
        config: EscalationConfig = {"enabled": True, "starting_model": "haiku"}
        assert config["enabled"] is True
        assert config["starting_model"] == "haiku"

    def test_can_construct_disabled_config(self):
        config: EscalationConfig = {"enabled": False, "starting_model": "sonnet"}
        assert config["enabled"] is False


class TestDefaultEscalationConfig:
    """default_escalation_config returns a sensible starting configuration."""

    def test_enabled_by_default(self):
        config = default_escalation_config()
        assert config["enabled"] is True

    def test_starts_at_haiku(self):
        config = default_escalation_config()
        assert config["starting_model"] == "haiku"


class TestEscalateModel:
    """escalate_model advances the model tier on failure."""

    def test_haiku_escalates_to_sonnet(self):
        assert escalate_model("haiku") == "sonnet"

    def test_sonnet_escalates_to_opus(self):
        assert escalate_model("sonnet") == "opus"

    def test_opus_stays_at_opus(self):
        """Escalation is capped at opus — no higher tier exists."""
        assert escalate_model("opus") == "opus"


class TestResetModel:
    """reset_model returns the configured starting tier."""

    def test_reset_to_haiku_from_opus(self):
        config: EscalationConfig = {"enabled": True, "starting_model": "haiku"}
        assert reset_model(config) == "haiku"

    def test_reset_to_sonnet_from_opus(self):
        config: EscalationConfig = {"enabled": True, "starting_model": "sonnet"}
        assert reset_model(config) == "sonnet"

    def test_reset_to_configured_starting_model(self):
        config: EscalationConfig = {"enabled": False, "starting_model": "opus"}
        assert reset_model(config) == "opus"


# ─── Tests: _escalate_node trace metadata ─────────────────────────────────────


def _make_task_state(**overrides) -> dict:
    """Build a minimal TaskState dict for escalate_node tests."""
    base = {
        "plan_path": "",
        "plan_data": None,
        "current_task_id": "1.1",
        "task_attempt": 2,
        "task_results": [],
        "effective_model": "haiku",
        "consecutive_failures": 1,
        "last_validation_verdict": "FAIL",
        "plan_cost_usd": 0.0,
        "plan_input_tokens": 0,
        "plan_output_tokens": 0,
    }
    base.update(overrides)
    return base


class TestEscalateNodeTraceMetadata:
    """_escalate_node emits pipeline_decision trace metadata on escalation."""

    def test_emits_escalate_decision(self):
        from langgraph_pipeline.executor.graph import _escalate_node

        state = _make_task_state(effective_model="haiku", task_attempt=1)
        with patch("langgraph_pipeline.executor.graph.add_trace_metadata") as mock_meta:
            _escalate_node(state)
        mock_meta.assert_called_once()
        call_kwargs = mock_meta.call_args[0][0]
        assert call_kwargs["decision"] == "escalate"
        assert call_kwargs["reason"] == "validator_failed_retry_available"

    def test_emits_from_and_to_model(self):
        from langgraph_pipeline.executor.graph import _escalate_node

        state = _make_task_state(effective_model="haiku", task_attempt=1)
        with patch("langgraph_pipeline.executor.graph.add_trace_metadata") as mock_meta:
            _escalate_node(state)
        call_kwargs = mock_meta.call_args[0][0]
        assert call_kwargs["from_model"] == "haiku"
        assert call_kwargs["to_model"] == "sonnet"

    def test_emits_cycle_number_from_task_attempt(self):
        from langgraph_pipeline.executor.graph import _escalate_node

        state = _make_task_state(effective_model="sonnet", task_attempt=2)
        with patch("langgraph_pipeline.executor.graph.add_trace_metadata") as mock_meta:
            _escalate_node(state)
        call_kwargs = mock_meta.call_args[0][0]
        assert call_kwargs["cycle_number"] == 2

    def test_escalate_node_still_returns_upgraded_model(self):
        from langgraph_pipeline.executor.graph import _escalate_node

        state = _make_task_state(effective_model="haiku")
        with patch("langgraph_pipeline.executor.graph.add_trace_metadata"):
            result = _escalate_node(state)
        assert result["effective_model"] == "sonnet"
        assert result["task_attempt"] == 1
