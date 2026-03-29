# tests/langgraph/executor/test_state.py
# Unit tests for the TaskState schema, related types, and effective_status helper.
# Design: docs/plans/2026-02-26-05-task-execution-subgraph-design.md
# Design: docs/plans/2026-03-28-73-three-state-task-lifecycle-design.md

"""Tests for langgraph_pipeline.executor.state."""

import operator
from typing import get_type_hints

from langgraph_pipeline.executor.state import (
    ModelTier,
    TaskResult,
    TaskState,
    TaskStatus,
    effective_status,
)


class TestModelTier:
    """ModelTier literal covers the three Claude model tiers."""

    def test_haiku_is_valid(self):
        value: ModelTier = "haiku"
        assert value == "haiku"

    def test_sonnet_is_valid(self):
        value: ModelTier = "sonnet"
        assert value == "sonnet"

    def test_opus_is_valid(self):
        value: ModelTier = "opus"
        assert value == "opus"


class TestTaskStatus:
    """TaskStatus literal covers all task lifecycle states."""

    def test_pending_is_valid(self):
        value: TaskStatus = "pending"
        assert value == "pending"

    def test_in_progress_is_valid(self):
        value: TaskStatus = "in_progress"
        assert value == "in_progress"

    def test_completed_is_valid(self):
        value: TaskStatus = "completed"
        assert value == "completed"

    def test_failed_is_valid(self):
        value: TaskStatus = "failed"
        assert value == "failed"

    def test_verified_is_valid(self):
        value: TaskStatus = "verified"
        assert value == "verified"

    def test_skipped_is_valid(self):
        value: TaskStatus = "skipped"
        assert value == "skipped"

    def test_all_six_states_exist(self):
        """AC7: TaskStatus contains exactly six states."""
        expected = {"pending", "in_progress", "completed", "verified", "failed", "skipped"}
        # Verify each expected value is assignable
        for status in expected:
            val: TaskStatus = status  # type: ignore[assignment]
            assert val == status


class TestTaskResult:
    """TaskResult is a TypedDict with the expected keys."""

    def test_required_keys_present(self):
        hints = get_type_hints(TaskResult)
        assert "task_id" in hints
        assert "status" in hints
        assert "model" in hints
        assert "cost_usd" in hints
        assert "input_tokens" in hints
        assert "output_tokens" in hints
        assert "message" in hints

    def test_can_construct_valid_result(self):
        result: TaskResult = {
            "task_id": "1.1",
            "status": "completed",
            "model": "haiku",
            "cost_usd": 0.001,
            "input_tokens": 500,
            "output_tokens": 200,
            "message": "Task completed successfully",
        }
        assert result["task_id"] == "1.1"
        assert result["status"] == "completed"
        assert result["model"] == "haiku"

    def test_can_construct_failed_result(self):
        result: TaskResult = {
            "task_id": "2.1",
            "status": "failed",
            "model": "sonnet",
            "cost_usd": 0.005,
            "input_tokens": 1000,
            "output_tokens": 100,
            "message": "Validation failed: assertion error",
        }
        assert result["status"] == "failed"


class TestTaskStateKeys:
    """TaskState TypedDict declares the full set of expected fields."""

    def _hints(self):
        return get_type_hints(TaskState, include_extras=True)

    def test_plan_reference_fields_present(self):
        hints = self._hints()
        assert "plan_path" in hints
        assert "plan_data" in hints

    def test_execution_context_fields_present(self):
        hints = self._hints()
        assert "current_task_id" in hints
        assert "task_attempt" in hints

    def test_task_results_field_present(self):
        hints = self._hints()
        assert "task_results" in hints

    def test_model_escalation_field_present(self):
        hints = self._hints()
        assert "effective_model" in hints

    def test_circuit_breaker_field_present(self):
        hints = self._hints()
        assert "consecutive_failures" in hints

    def test_cost_accumulator_fields_present(self):
        hints = self._hints()
        assert "plan_cost_usd" in hints
        assert "plan_input_tokens" in hints
        assert "plan_output_tokens" in hints


class TestTaskResultsReducer:
    """task_results uses operator.add so LangGraph appends instead of replacing."""

    def test_reducer_is_operator_add(self):
        hints = get_type_hints(TaskState, include_extras=True)
        annotation = hints["task_results"]
        metadata = annotation.__metadata__
        assert operator.add in metadata

    def test_operator_add_merges_lists(self):
        """Verify operator.add appends task results from parallel branches."""
        branch_a: list[TaskResult] = [
            {
                "task_id": "1.1",
                "status": "completed",
                "model": "haiku",
                "cost_usd": 0.001,
                "input_tokens": 100,
                "output_tokens": 50,
                "message": "done",
            }
        ]
        branch_b: list[TaskResult] = [
            {
                "task_id": "1.2",
                "status": "completed",
                "model": "haiku",
                "cost_usd": 0.002,
                "input_tokens": 200,
                "output_tokens": 80,
                "message": "done",
            }
        ]
        merged = operator.add(branch_a, branch_b)
        assert len(merged) == 2
        assert merged[0]["task_id"] == "1.1"
        assert merged[1]["task_id"] == "1.2"


# ─── effective_status tests ──────────────────────────────────────────────────

# Reusable validation config fixtures
_VALIDATION_ENABLED = {"enabled": True, "run_after": ["coder", "frontend-coder"]}
_VALIDATION_DISABLED = {"enabled": False}
_VALIDATION_EMPTY = {}


class TestEffectiveStatusNonCompleted:
    """effective_status passes through all non-completed statuses unchanged."""

    def test_pending_unchanged(self):
        task = {"status": "pending", "agent": "coder"}
        assert effective_status(task, _VALIDATION_ENABLED) == "pending"

    def test_in_progress_unchanged(self):
        task = {"status": "in_progress", "agent": "coder"}
        assert effective_status(task, _VALIDATION_ENABLED) == "in_progress"

    def test_verified_unchanged(self):
        task = {"status": "verified", "agent": "coder"}
        assert effective_status(task, _VALIDATION_ENABLED) == "verified"

    def test_failed_unchanged(self):
        task = {"status": "failed", "agent": "coder"}
        assert effective_status(task, _VALIDATION_ENABLED) == "failed"

    def test_skipped_unchanged(self):
        task = {"status": "skipped", "agent": "coder"}
        assert effective_status(task, _VALIDATION_ENABLED) == "skipped"


class TestEffectiveStatusValidationDisabled:
    """AC18: completed -> verified when validation is not enabled."""

    def test_completed_becomes_verified_when_disabled(self):
        task = {"status": "completed", "agent": "coder"}
        assert effective_status(task, _VALIDATION_DISABLED) == "verified"

    def test_completed_becomes_verified_when_empty_meta(self):
        task = {"status": "completed", "agent": "coder"}
        assert effective_status(task, _VALIDATION_EMPTY) == "verified"


class TestEffectiveStatusAgentNotInRunAfter:
    """AC18: completed -> verified when agent not in run_after list."""

    def test_completed_becomes_verified_for_excluded_agent(self):
        task = {"status": "completed", "agent": "systems-designer"}
        validation = {"enabled": True, "run_after": ["coder", "frontend-coder"]}
        assert effective_status(task, validation) == "verified"

    def test_completed_stays_completed_for_included_agent(self):
        """AC20: genuinely awaiting validation stays completed."""
        task = {"status": "completed", "agent": "coder"}
        validation = {"enabled": True, "run_after": ["coder", "frontend-coder"]}
        assert effective_status(task, validation) == "completed"

    def test_empty_run_after_keeps_all_agents_awaiting_validation(self):
        """Empty run_after with validation enabled: all agents require validation."""
        task = {"status": "completed", "agent": "coder"}
        validation = {"enabled": True, "run_after": []}
        assert effective_status(task, validation) == "completed"


class TestEffectiveStatusValidationAttempts:
    """AC18/AC20: completed -> verified when task already went through validation."""

    def test_completed_with_validation_attempts_becomes_verified(self):
        task = {"status": "completed", "agent": "coder", "validation_attempts": 1}
        assert effective_status(task, _VALIDATION_ENABLED) == "verified"

    def test_completed_with_zero_attempts_stays_completed(self):
        """AC20: zero attempts means validation hasn't run yet."""
        task = {"status": "completed", "agent": "coder", "validation_attempts": 0}
        assert effective_status(task, _VALIDATION_ENABLED) == "completed"

    def test_completed_with_no_attempts_key_stays_completed(self):
        """AC20: missing validation_attempts key means no validation has run."""
        task = {"status": "completed", "agent": "coder"}
        assert effective_status(task, _VALIDATION_ENABLED) == "completed"

    def test_completed_with_multiple_attempts_becomes_verified(self):
        task = {"status": "completed", "agent": "coder", "validation_attempts": 3}
        assert effective_status(task, _VALIDATION_ENABLED) == "verified"


class TestEffectiveStatusDefaultAgent:
    """effective_status defaults agent to 'coder' when not specified."""

    def test_missing_agent_defaults_to_coder(self):
        task = {"status": "completed"}
        validation = {"enabled": True, "run_after": ["coder"]}
        # coder is in run_after and no validation_attempts -> stays completed
        assert effective_status(task, validation) == "completed"

    def test_missing_agent_not_in_run_after(self):
        task = {"status": "completed"}
        validation = {"enabled": True, "run_after": ["frontend-coder"]}
        # default coder is NOT in run_after -> promoted to verified
        assert effective_status(task, validation) == "verified"


class TestEffectiveStatusMissingStatusKey:
    """effective_status handles tasks with missing status key gracefully."""

    def test_missing_status_defaults_to_pending(self):
        task = {"agent": "coder"}
        assert effective_status(task, _VALIDATION_ENABLED) == "pending"
