# tests/langgraph/web/test_tool_call_attribution.py
# Unit tests for TracingProxy.get_tool_call_attribution() and ToolCallCost.
# Design: docs/plans/2026-03-27-11-tool-call-cost-attribution-design.md

"""Unit tests for the tool-call cost attribution logic in TracingProxy."""

import json
from datetime import datetime, timezone

import pytest

from langgraph_pipeline.web.proxy import ToolCallCost, TracingProxy

# ─── Constants ────────────────────────────────────────────────────────────────

SAMPLE_ITEM_SLUG = "11-tool-call-cost-attribution"
SAMPLE_ITEM_TYPE = "feature"
SAMPLE_TASK_ID = "1.1"
SAMPLE_AGENT_TYPE = "coder"
SAMPLE_MODEL = "claude-sonnet-4-6"
SAMPLE_INPUT_TOKENS = 15000
SAMPLE_OUTPUT_TOKENS = 4200
SAMPLE_COST_USD = 0.0312
SAMPLE_DURATION_S = 62.5

TOOL_CALLS_TWO_READS = [
    {"tool": "Read", "file_path": "src/foo.py", "result_bytes": 3000},
    {"tool": "Read", "file_path": "src/bar.py", "result_bytes": 1000},
]

TOOL_CALLS_WITH_ZERO = [
    {"tool": "Edit", "file_path": "src/main.py", "result_bytes": 0},
    {"tool": "Bash", "command": "pytest tests/", "result_bytes": 2500},
]

TOOL_CALLS_MIXED = [
    {"tool": "Glob", "pattern": "**/*.py", "result_bytes": 800},
    {"tool": "Grep", "pattern": "class Foo", "result_bytes": 400},
    {"tool": "Bash", "command": "git status --short", "result_bytes": 200},
]

RECORDED_AT = datetime.now(timezone.utc).isoformat()


# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def proxy(tmp_path):
    """Create a TracingProxy backed by a temp-dir SQLite DB."""
    db_path = str(tmp_path / "test-traces.db")
    return TracingProxy({"db_path": db_path, "forward_to_langsmith": False})


def _insert_cost_task(proxy, item_slug, task_id, cost_usd, tool_calls):
    """Helper: insert a cost_tasks row with the given tool calls."""
    proxy.record_cost_task(
        item_slug=item_slug,
        item_type=SAMPLE_ITEM_TYPE,
        task_id=task_id,
        agent_type=SAMPLE_AGENT_TYPE,
        model=SAMPLE_MODEL,
        input_tokens=SAMPLE_INPUT_TOKENS,
        output_tokens=SAMPLE_OUTPUT_TOKENS,
        cost_usd=cost_usd,
        duration_s=SAMPLE_DURATION_S,
        tool_calls_json=json.dumps(tool_calls),
        recorded_at=RECORDED_AT,
    )


# ─── get_tool_call_attribution Tests ──────────────────────────────────────────


def test_attribution_empty_db_returns_empty(proxy):
    """Returns an empty list when cost_tasks has no rows."""
    result = proxy.get_tool_call_attribution()
    assert result == []


def test_attribution_proportional_split(proxy):
    """Cost is split proportionally by result_bytes across tool calls."""
    cost = 0.0400
    _insert_cost_task(proxy, SAMPLE_ITEM_SLUG, SAMPLE_TASK_ID, cost, TOOL_CALLS_TWO_READS)

    result = proxy.get_tool_call_attribution()

    # Two Read calls: 3000 bytes and 1000 bytes, total 4000
    assert len(result) == 2
    assert all(isinstance(tc, ToolCallCost) for tc in result)

    # Sort by result_bytes descending to match expected proportions
    by_bytes = sorted(result, key=lambda tc: tc.result_bytes, reverse=True)
    large, small = by_bytes[0], by_bytes[1]

    assert large.result_bytes == 3000
    assert small.result_bytes == 1000
    assert abs(large.estimated_cost_usd - cost * 0.75) < 1e-9
    assert abs(small.estimated_cost_usd - cost * 0.25) < 1e-9


def test_attribution_zero_bytes_tool_excluded(proxy):
    """Tool calls with result_bytes == 0 are excluded from attribution."""
    _insert_cost_task(proxy, SAMPLE_ITEM_SLUG, SAMPLE_TASK_ID, 0.0200, TOOL_CALLS_WITH_ZERO)

    result = proxy.get_tool_call_attribution()

    # Only Bash (2500 bytes) should appear; Edit (0 bytes) is excluded
    assert len(result) == 1
    assert result[0].tool_name == "Bash"
    assert result[0].result_bytes == 2500


def test_attribution_all_zero_bytes_excluded(proxy):
    """When all tool calls have 0 result_bytes, the task is skipped entirely."""
    zero_calls = [
        {"tool": "Edit", "file_path": "a.py", "result_bytes": 0},
        {"tool": "Write", "file_path": "b.py", "result_bytes": 0},
    ]
    _insert_cost_task(proxy, SAMPLE_ITEM_SLUG, SAMPLE_TASK_ID, 0.0100, zero_calls)

    result = proxy.get_tool_call_attribution()
    assert result == []


def test_attribution_null_tool_calls_json_skipped(proxy):
    """Rows with tool_calls_json IS NULL are skipped (no attribution)."""
    proxy.record_cost_task(
        item_slug=SAMPLE_ITEM_SLUG,
        item_type=SAMPLE_ITEM_TYPE,
        task_id=SAMPLE_TASK_ID,
        agent_type=SAMPLE_AGENT_TYPE,
        model=SAMPLE_MODEL,
        input_tokens=SAMPLE_INPUT_TOKENS,
        output_tokens=SAMPLE_OUTPUT_TOKENS,
        cost_usd=0.0100,
        duration_s=SAMPLE_DURATION_S,
        tool_calls_json=None,
        recorded_at=RECORDED_AT,
    )

    result = proxy.get_tool_call_attribution()
    assert result == []


def test_attribution_invalid_json_skipped(proxy):
    """Rows with malformed tool_calls_json are silently skipped."""
    proxy.record_cost_task(
        item_slug=SAMPLE_ITEM_SLUG,
        item_type=SAMPLE_ITEM_TYPE,
        task_id=SAMPLE_TASK_ID,
        agent_type=SAMPLE_AGENT_TYPE,
        model=SAMPLE_MODEL,
        input_tokens=SAMPLE_INPUT_TOKENS,
        output_tokens=SAMPLE_OUTPUT_TOKENS,
        cost_usd=0.0100,
        duration_s=SAMPLE_DURATION_S,
        tool_calls_json="not valid json {{",
        recorded_at=RECORDED_AT,
    )

    result = proxy.get_tool_call_attribution()
    assert result == []


def test_attribution_sorted_by_cost_descending(proxy):
    """Results are sorted by estimated_cost_usd descending."""
    _insert_cost_task(proxy, SAMPLE_ITEM_SLUG, SAMPLE_TASK_ID, 0.0600, TOOL_CALLS_MIXED)

    result = proxy.get_tool_call_attribution()

    costs = [tc.estimated_cost_usd for tc in result]
    assert costs == sorted(costs, reverse=True)


def test_attribution_multiple_tasks_aggregated(proxy):
    """Tool calls from multiple tasks are all included in the result."""
    _insert_cost_task(proxy, "slug-a", "1.1", 0.0200, TOOL_CALLS_TWO_READS)
    _insert_cost_task(proxy, "slug-b", "2.1", 0.0100, TOOL_CALLS_MIXED)

    result = proxy.get_tool_call_attribution()

    # 2 from slug-a, 3 from slug-b
    assert len(result) == 5
    slugs = {tc.item_slug for tc in result}
    assert slugs == {"slug-a", "slug-b"}


def test_attribution_item_slug_and_task_id_preserved(proxy):
    """Each ToolCallCost carries the item_slug and task_id from its row."""
    _insert_cost_task(proxy, SAMPLE_ITEM_SLUG, "3.2", 0.0100, TOOL_CALLS_TWO_READS)

    result = proxy.get_tool_call_attribution()

    for tc in result:
        assert tc.item_slug == SAMPLE_ITEM_SLUG
        assert tc.task_id == "3.2"


def test_attribution_detail_file_path(proxy):
    """Read/Edit calls use file_path as the detail field."""
    calls = [{"tool": "Read", "file_path": "src/foo.py", "result_bytes": 1000}]
    _insert_cost_task(proxy, SAMPLE_ITEM_SLUG, SAMPLE_TASK_ID, 0.0050, calls)

    result = proxy.get_tool_call_attribution()

    assert len(result) == 1
    assert result[0].detail == "src/foo.py"


def test_attribution_detail_bash_command_truncated(proxy):
    """Bash calls use a truncated command as the detail field."""
    long_command = "pytest tests/ -v --tb=short --no-header " * 5
    calls = [{"tool": "Bash", "command": long_command, "result_bytes": 500}]
    _insert_cost_task(proxy, SAMPLE_ITEM_SLUG, SAMPLE_TASK_ID, 0.0010, calls)

    result = proxy.get_tool_call_attribution()

    assert len(result) == 1
    assert len(result[0].detail) <= 50


def test_attribution_capped_at_top_tool_calls_limit(proxy):
    """Result is capped at TOP_TOOL_CALLS_LIMIT (250) entries."""
    from langgraph_pipeline.web.proxy import TOP_TOOL_CALLS_LIMIT

    large_tool_calls = [
        {"tool": "Read", "file_path": f"file_{i}.py", "result_bytes": 100 + i}
        for i in range(TOP_TOOL_CALLS_LIMIT + 50)
    ]
    _insert_cost_task(proxy, SAMPLE_ITEM_SLUG, SAMPLE_TASK_ID, 1.0000, large_tool_calls)

    result = proxy.get_tool_call_attribution()
    assert len(result) == TOP_TOOL_CALLS_LIMIT
