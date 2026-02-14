# tests/test_token_usage.py
# Unit tests for TaskUsage dataclass and parse_task_usage helper.
# Design ref: docs/plans/2026-02-14-06-token-usage-tracking-design.md

import importlib.util
import sys

# plan-orchestrator.py has a hyphen in the filename, so we must use importlib
# to load it as a module under a valid Python identifier.
spec = importlib.util.spec_from_file_location(
    "plan_orchestrator", "scripts/plan-orchestrator.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

TaskUsage = mod.TaskUsage
parse_task_usage = mod.parse_task_usage


# --- TaskUsage dataclass tests ---


def test_task_usage_defaults():
    """All fields should default to zero."""
    usage = TaskUsage()
    assert usage.input_tokens == 0
    assert usage.output_tokens == 0
    assert usage.cache_read_tokens == 0
    assert usage.cache_creation_tokens == 0
    assert usage.total_cost_usd == 0.0
    assert usage.num_turns == 0
    assert usage.duration_api_ms == 0


# --- parse_task_usage tests ---


def test_parse_task_usage_full():
    """Realistic result dict should populate all fields correctly."""
    result_data = {
        "total_cost_usd": 0.49,
        "usage": {
            "input_tokens": 10,
            "output_tokens": 2782,
            "cache_read_input_tokens": 417890,
            "cache_creation_input_tokens": 34206,
        },
        "num_turns": 5,
        "duration_api_ms": 45000,
    }
    usage = parse_task_usage(result_data)
    assert usage.input_tokens == 10
    assert usage.output_tokens == 2782
    assert usage.cache_read_tokens == 417890
    assert usage.cache_creation_tokens == 34206
    assert usage.total_cost_usd == 0.49
    assert usage.num_turns == 5
    assert usage.duration_api_ms == 45000


def test_parse_task_usage_empty():
    """Empty dict should produce all-zero TaskUsage."""
    usage = parse_task_usage({})
    assert usage.input_tokens == 0
    assert usage.output_tokens == 0
    assert usage.cache_read_tokens == 0
    assert usage.cache_creation_tokens == 0
    assert usage.total_cost_usd == 0.0
    assert usage.num_turns == 0
    assert usage.duration_api_ms == 0


def test_parse_task_usage_partial():
    """Only total_cost_usd provided; token fields should be zero."""
    result_data = {"total_cost_usd": 1.23}
    usage = parse_task_usage(result_data)
    assert usage.total_cost_usd == 1.23
    assert usage.input_tokens == 0
    assert usage.output_tokens == 0
    assert usage.cache_read_tokens == 0
    assert usage.cache_creation_tokens == 0
    assert usage.num_turns == 0
    assert usage.duration_api_ms == 0


def test_parse_task_usage_missing_usage_key():
    """Dict with cost but no 'usage' key should set cost, tokens stay zero."""
    result_data = {
        "total_cost_usd": 0.55,
        "num_turns": 3,
        "duration_api_ms": 12000,
    }
    usage = parse_task_usage(result_data)
    assert usage.total_cost_usd == 0.55
    assert usage.num_turns == 3
    assert usage.duration_api_ms == 12000
    assert usage.input_tokens == 0
    assert usage.output_tokens == 0
    assert usage.cache_read_tokens == 0
    assert usage.cache_creation_tokens == 0
