# tests/langgraph/executor/test_state.py
# Unit tests for the TaskState schema and related types.
# Design: docs/plans/2026-02-26-05-task-execution-subgraph-design.md

"""Tests for langgraph_pipeline.executor.state."""

import operator
from typing import get_type_hints

from langgraph_pipeline.executor.state import (
    ModelTier,
    TaskResult,
    TaskState,
    TaskStatus,
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

    def test_skipped_is_valid(self):
        value: TaskStatus = "skipped"
        assert value == "skipped"


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
