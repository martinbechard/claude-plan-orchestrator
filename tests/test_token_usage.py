# tests/test_token_usage.py
# Unit tests for TaskUsage, parse_task_usage, and PlanUsageTracker.
# Design ref: docs/plans/2026-02-14-06-token-usage-tracking-design.md

import importlib.util
import json

from pytest import approx
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
PlanUsageTracker = mod.PlanUsageTracker


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


# --- PlanUsageTracker tests ---


def test_tracker_record_and_total():
    """Recording two tasks should produce correct aggregate totals."""
    tracker = PlanUsageTracker()
    tracker.record("1.1", TaskUsage(
        input_tokens=100, output_tokens=200,
        cache_read_tokens=50, cache_creation_tokens=10,
        total_cost_usd=0.10, num_turns=3, duration_api_ms=5000,
    ))
    tracker.record("1.2", TaskUsage(
        input_tokens=300, output_tokens=400,
        cache_read_tokens=150, cache_creation_tokens=20,
        total_cost_usd=0.25, num_turns=5, duration_api_ms=8000,
    ))
    total = tracker.get_total_usage()
    assert total.input_tokens == 400
    assert total.output_tokens == 600
    assert total.cache_read_tokens == 200
    assert total.cache_creation_tokens == 30
    assert total.total_cost_usd == 0.35
    assert total.num_turns == 8
    assert total.duration_api_ms == 13000


def test_tracker_cache_hit_rate():
    """Cache hit rate should be cache_read / (cache_read + input_tokens)."""
    tracker = PlanUsageTracker()
    tracker.record("1.1", TaskUsage(
        input_tokens=100, cache_read_tokens=300,
    ))
    assert tracker.get_cache_hit_rate() == 0.75


def test_tracker_cache_hit_rate_zero():
    """Empty tracker should return 0.0 cache hit rate."""
    tracker = PlanUsageTracker()
    assert tracker.get_cache_hit_rate() == 0.0


def test_tracker_section_usage():
    """Section usage should aggregate only tasks belonging to that section."""
    tracker = PlanUsageTracker()
    tracker.record("1.1", TaskUsage(
        input_tokens=100, total_cost_usd=0.10,
    ))
    tracker.record("1.2", TaskUsage(
        input_tokens=200, total_cost_usd=0.20,
    ))
    tracker.record("2.1", TaskUsage(
        input_tokens=500, total_cost_usd=0.50,
    ))
    plan = {
        "sections": [
            {
                "id": "phase-1",
                "name": "Phase 1",
                "tasks": [
                    {"id": "1.1"},
                    {"id": "1.2"},
                ],
            },
            {
                "id": "phase-2",
                "name": "Phase 2",
                "tasks": [
                    {"id": "2.1"},
                ],
            },
        ],
    }
    s1 = tracker.get_section_usage(plan, "phase-1")
    assert s1.input_tokens == 300
    assert s1.total_cost_usd == approx(0.30)

    s2 = tracker.get_section_usage(plan, "phase-2")
    assert s2.input_tokens == 500
    assert s2.total_cost_usd == approx(0.50)


def test_tracker_format_summary_line():
    """Summary line should contain task id, cost, and token counts."""
    tracker = PlanUsageTracker()
    tracker.record("1.1", TaskUsage(
        input_tokens=1234, output_tokens=567, cache_read_tokens=890,
        total_cost_usd=0.0234,
    ))
    line = tracker.format_summary_line("1.1")
    assert "[Usage] Task" in line
    assert "1.1" in line
    assert "$0.0234" in line
    assert "1,234" in line
    assert "567" in line
    assert "890" in line


def test_tracker_format_final_summary():
    """Final summary should contain header, total cost, and section breakdown."""
    tracker = PlanUsageTracker()
    tracker.record("1.1", TaskUsage(
        input_tokens=100, output_tokens=200, total_cost_usd=0.10,
    ))
    tracker.record("2.1", TaskUsage(
        input_tokens=300, output_tokens=400, total_cost_usd=0.30,
    ))
    plan = {
        "sections": [
            {
                "id": "phase-1",
                "name": "Phase 1",
                "tasks": [{"id": "1.1"}],
            },
            {
                "id": "phase-2",
                "name": "Phase 2",
                "tasks": [{"id": "2.1"}],
            },
        ],
    }
    summary = tracker.format_final_summary(plan)
    assert "=== Usage Summary (API-Equivalent Estimates) ===" in summary
    assert "~$0.4000" in summary
    assert "Total API-equivalent cost:" in summary
    assert "not actual subscription charges" in summary
    assert "Phase 1" in summary
    assert "Phase 2" in summary
    assert "~$0.1000" in summary
    assert "~$0.3000" in summary


def test_tracker_write_report(tmp_path, monkeypatch):
    """write_report() should create a JSON file with expected keys."""
    monkeypatch.setattr(mod, "TASK_LOG_DIR", tmp_path)

    tracker = PlanUsageTracker()
    tracker.record("1.1", TaskUsage(
        input_tokens=100, output_tokens=200, cache_read_tokens=50,
        cache_creation_tokens=10, total_cost_usd=0.10,
        num_turns=3, duration_api_ms=5000,
    ))
    tracker.record("2.1", TaskUsage(
        input_tokens=300, output_tokens=400, cache_read_tokens=150,
        cache_creation_tokens=20, total_cost_usd=0.25,
        num_turns=5, duration_api_ms=8000,
    ))
    plan = {
        "meta": {"name": "Test Plan"},
        "sections": [
            {
                "id": "phase-1",
                "name": "Phase 1",
                "tasks": [{"id": "1.1"}],
            },
            {
                "id": "phase-2",
                "name": "Phase 2",
                "tasks": [{"id": "2.1"}],
            },
        ],
    }
    report_path = tracker.write_report(plan, str(tmp_path / "plan.yaml"))
    assert report_path is not None
    assert report_path.exists()

    with open(report_path) as f:
        report = json.load(f)

    assert report["plan_name"] == "Test Plan"
    assert "total" in report
    assert report["total"]["cost_usd"] == 0.35
    assert report["total"]["input_tokens"] == 400
    assert "sections" in report
    assert len(report["sections"]) == 2
    assert "tasks" in report
    assert len(report["tasks"]) == 2
