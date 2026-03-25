# tests/langgraph/web/test_cost_log_reader.py
# Unit tests for CostLogReader aggregation functions and svg_bar_chart helper.
# Design: docs/plans/2026-03-25-16-tool-call-timing-and-cost-analysis-ui-design.md

"""Tests for langgraph_pipeline.web.cost_log_reader and /analysis route."""

import json
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from langgraph_pipeline.web.cost_log_reader import CostLogReader, svg_bar_chart

# ─── Constants ────────────────────────────────────────────────────────────────

TOP_FILES_LIMIT = 20
FIXTURE_ITEM_SLUG = "test-feature-slug"
FIXTURE_ITEM_TYPE = "feature"

# ─── Fixtures ─────────────────────────────────────────────────────────────────


def _make_task(
    task_id: str,
    agent_type: str = "coder",
    model: str = "sonnet",
    input_tokens: int = 1000,
    output_tokens: int = 200,
    cost_usd: float = 0.01,
    duration_s: float = 10.0,
    tool_calls: list | None = None,
) -> dict:
    return {
        "task_id": task_id,
        "agent_type": agent_type,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost_usd,
        "duration_s": duration_s,
        "tool_calls": tool_calls or [],
    }


def _make_log(item_slug: str, item_type: str, tasks: list[dict]) -> dict:
    return {"item_slug": item_slug, "item_type": item_type, "tasks": tasks}


def _write_log(directory: Path, filename: str, data: dict) -> None:
    (directory / filename).write_text(json.dumps(data), encoding="utf-8")


# ─── CostLogReader.load_all() tests ───────────────────────────────────────────


def test_load_all_empty_dir():
    """load_all() on a missing directory returns CostData with has_data=False."""
    missing = Path(tempfile.mkdtemp()) / "does-not-exist"
    reader = CostLogReader(logs_dir=missing)
    result = reader.load_all()

    assert result.has_data is False
    assert result.top_files == []
    assert result.cost_by_agent == {}
    assert result.cost_by_item == []
    assert result.wasted_reads == []


def test_load_all_single_file():
    """load_all() on a directory with one valid JSON returns aggregated CostData."""
    with tempfile.TemporaryDirectory() as tmp:
        logs_dir = Path(tmp)
        tasks = [
            _make_task(
                "1.1",
                agent_type="coder",
                input_tokens=2000,
                output_tokens=500,
                cost_usd=0.05,
                tool_calls=[
                    {"tool": "Read", "file_path": "src/foo.py", "result_bytes": 3200},
                    {"tool": "Bash", "command": "pytest", "result_bytes": 512},
                ],
            ),
            _make_task(
                "1.2",
                agent_type="validator",
                input_tokens=1000,
                output_tokens=100,
                cost_usd=0.02,
            ),
        ]
        _write_log(logs_dir, f"{FIXTURE_ITEM_SLUG}.json", _make_log(FIXTURE_ITEM_SLUG, FIXTURE_ITEM_TYPE, tasks))

        reader = CostLogReader(logs_dir=logs_dir)
        result = reader.load_all()

    assert result.has_data is True
    assert len(result.cost_by_item) == 1
    item = result.cost_by_item[0]
    assert item.item_slug == FIXTURE_ITEM_SLUG
    assert item.num_tasks == 2
    assert "coder" in item.agent_types
    assert "validator" in item.agent_types

    assert "src/foo.py" in dict(result.top_files)
    assert dict(result.top_files)["src/foo.py"] == 3200

    assert "coder" in result.cost_by_agent
    assert result.cost_by_agent["coder"] == 2000 + 500
    assert result.cost_by_agent["validator"] == 1000 + 100

    assert result.wasted_reads == []


def test_top_files_capped_at_20():
    """load_all() returns at most 20 entries in top_files even with 25 distinct paths."""
    with tempfile.TemporaryDirectory() as tmp:
        logs_dir = Path(tmp)
        tool_calls = [
            {"tool": "Read", "file_path": f"src/file_{i}.py", "result_bytes": 100 * (25 - i)}
            for i in range(25)
        ]
        tasks = [_make_task("1.1", tool_calls=tool_calls)]
        _write_log(logs_dir, f"{FIXTURE_ITEM_SLUG}.json", _make_log(FIXTURE_ITEM_SLUG, FIXTURE_ITEM_TYPE, tasks))

        reader = CostLogReader(logs_dir=logs_dir)
        result = reader.load_all()

    assert len(result.top_files) == TOP_FILES_LIMIT


def test_wasted_reads_detected():
    """A file_path read in 2 distinct tasks appears in wasted_reads."""
    with tempfile.TemporaryDirectory() as tmp:
        logs_dir = Path(tmp)
        shared_path = "src/shared.py"
        tasks = [
            _make_task("1.1", tool_calls=[{"tool": "Read", "file_path": shared_path, "result_bytes": 100}]),
            _make_task("1.2", tool_calls=[{"tool": "Read", "file_path": shared_path, "result_bytes": 100}]),
        ]
        _write_log(logs_dir, f"{FIXTURE_ITEM_SLUG}.json", _make_log(FIXTURE_ITEM_SLUG, FIXTURE_ITEM_TYPE, tasks))

        reader = CostLogReader(logs_dir=logs_dir)
        result = reader.load_all()

    wasted_paths = [wr.file_path for wr in result.wasted_reads]
    assert shared_path in wasted_paths
    matching = next(wr for wr in result.wasted_reads if wr.file_path == shared_path)
    assert matching.task_count == 2
    assert matching.item_slug == FIXTURE_ITEM_SLUG


def test_wasted_reads_no_false_positive():
    """A file_path read multiple times in the same task must NOT appear in wasted_reads."""
    with tempfile.TemporaryDirectory() as tmp:
        logs_dir = Path(tmp)
        shared_path = "src/shared.py"
        tasks = [
            _make_task(
                "1.1",
                tool_calls=[
                    {"tool": "Read", "file_path": shared_path, "result_bytes": 100},
                    {"tool": "Read", "file_path": shared_path, "result_bytes": 100},
                ],
            ),
        ]
        _write_log(logs_dir, f"{FIXTURE_ITEM_SLUG}.json", _make_log(FIXTURE_ITEM_SLUG, FIXTURE_ITEM_TYPE, tasks))

        reader = CostLogReader(logs_dir=logs_dir)
        result = reader.load_all()

    wasted_paths = [wr.file_path for wr in result.wasted_reads]
    assert shared_path not in wasted_paths


# ─── svg_bar_chart() tests ────────────────────────────────────────────────────


def test_svg_bar_chart_returns_svg_string():
    """svg_bar_chart() with valid data returns a string starting with '<svg'."""
    result = svg_bar_chart(
        labels=["src/a.py", "src/b.py"],
        values=[500, 200],
        width=700,
        bar_height=18,
        title="Test Chart",
    )
    assert result.startswith("<svg")


def test_svg_bar_chart_empty_data_returns_svg():
    """svg_bar_chart() with no data still returns an SVG string."""
    result = svg_bar_chart(labels=[], values=[], width=700, bar_height=18, title="Empty")
    assert result.startswith("<svg")


# ─── /analysis endpoint integration tests ─────────────────────────────────────


@pytest.fixture()
def client_no_data(tmp_path):
    """TestClient with CostLogReader pointed at an empty directory."""
    from unittest.mock import patch

    from langgraph_pipeline.web.server import create_app

    empty_logs = tmp_path / "empty-logs"
    empty_logs.mkdir()

    app = create_app(config={})
    with patch(
        "langgraph_pipeline.web.routes.analysis.CostLogReader",
        return_value=CostLogReader(logs_dir=empty_logs),
    ):
        yield TestClient(app)


@pytest.fixture()
def client_with_data(tmp_path):
    """TestClient with CostLogReader pointed at a directory with one fixture file."""
    from unittest.mock import patch

    from langgraph_pipeline.web.server import create_app

    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()

    tasks = [_make_task("1.1", agent_type="coder", input_tokens=1000, output_tokens=200, cost_usd=0.03)]
    _write_log(logs_dir, f"{FIXTURE_ITEM_SLUG}.json", _make_log(FIXTURE_ITEM_SLUG, FIXTURE_ITEM_TYPE, tasks))

    app = create_app(config={})
    with patch(
        "langgraph_pipeline.web.routes.analysis.CostLogReader",
        return_value=CostLogReader(logs_dir=logs_dir),
    ):
        yield TestClient(app)


def test_analysis_endpoint_no_data(client_no_data):
    """GET /analysis with empty log dir returns 200 and empty-state message in body."""
    response = client_no_data.get("/analysis")
    assert response.status_code == 200
    assert "No cost data yet" in response.text


def test_analysis_endpoint_with_data(client_with_data):
    """GET /analysis with one fixture file returns 200 and item slug in body."""
    response = client_with_data.get("/analysis")
    assert response.status_code == 200
    assert FIXTURE_ITEM_SLUG in response.text
