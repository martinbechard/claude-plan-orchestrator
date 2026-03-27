# tests/langgraph/web/test_cost_log_reader.py
# Unit tests for CostLogReader aggregation functions and svg_bar_chart helper.
# Design: docs/plans/2026-03-25-16-tool-call-timing-and-cost-analysis-ui-design.md

"""Tests for langgraph_pipeline.web.cost_log_reader and /analysis route."""

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from langgraph_pipeline.web.cost_log_reader import CostLogReader, svg_bar_chart

# ─── Constants ────────────────────────────────────────────────────────────────

TOP_FILES_LIMIT = 20
FIXTURE_ITEM_SLUG = "test-feature-slug"
FIXTURE_ITEM_TYPE = "feature"
NONEXISTENT_DB = "/tmp/does-not-exist-cost-reader-test.db"

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


def _create_db_with_tasks(db_path: Path, rows: list[dict]) -> None:
    """Create a SQLite DB with cost_tasks table populated with the given rows."""
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE cost_tasks (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            item_slug       TEXT NOT NULL,
            item_type       TEXT NOT NULL,
            task_id         TEXT NOT NULL,
            agent_type      TEXT NOT NULL,
            model           TEXT NOT NULL,
            input_tokens    INTEGER NOT NULL DEFAULT 0,
            output_tokens   INTEGER NOT NULL DEFAULT 0,
            cost_usd        REAL NOT NULL DEFAULT 0.0,
            duration_s      REAL NOT NULL DEFAULT 0.0,
            tool_calls_json TEXT,
            recorded_at     TEXT NOT NULL
        )
        """
    )
    for row in rows:
        conn.execute(
            """
            INSERT INTO cost_tasks
                (item_slug, item_type, task_id, agent_type, model,
                 input_tokens, output_tokens, cost_usd, duration_s,
                 tool_calls_json, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                row["item_slug"],
                row["item_type"],
                row["task_id"],
                row["agent_type"],
                row["model"],
                row["input_tokens"],
                row["output_tokens"],
                row["cost_usd"],
                row["duration_s"],
                row.get("tool_calls_json"),
                row.get("recorded_at", "2026-01-01T00:00:00+00:00"),
            ],
        )
    conn.commit()
    conn.close()


# ─── CostLogReader.load_all() JSON fallback tests ─────────────────────────────


def test_load_all_empty_dir():
    """load_all() on a missing directory (with no DB) returns CostData with has_data=False."""
    missing = Path(tempfile.mkdtemp()) / "does-not-exist"
    reader = CostLogReader(logs_dir=missing, db_path=NONEXISTENT_DB)
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

        reader = CostLogReader(logs_dir=logs_dir, db_path=NONEXISTENT_DB)
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

        reader = CostLogReader(logs_dir=logs_dir, db_path=NONEXISTENT_DB)
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

        reader = CostLogReader(logs_dir=logs_dir, db_path=NONEXISTENT_DB)
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

        reader = CostLogReader(logs_dir=logs_dir, db_path=NONEXISTENT_DB)
        result = reader.load_all()

    wasted_paths = [wr.file_path for wr in result.wasted_reads]
    assert shared_path not in wasted_paths


# ─── CostLogReader DB path tests ──────────────────────────────────────────────


def test_load_all_from_db_basic(tmp_path):
    """load_all() reads from DB when it exists and cost_tasks table is present."""
    db_path = tmp_path / "test.db"
    _create_db_with_tasks(
        db_path,
        [
            {
                "item_slug": FIXTURE_ITEM_SLUG,
                "item_type": FIXTURE_ITEM_TYPE,
                "task_id": "1.1",
                "agent_type": "coder",
                "model": "sonnet",
                "input_tokens": 2000,
                "output_tokens": 500,
                "cost_usd": 0.05,
                "duration_s": 15.0,
                "tool_calls_json": None,
            },
            {
                "item_slug": FIXTURE_ITEM_SLUG,
                "item_type": FIXTURE_ITEM_TYPE,
                "task_id": "1.2",
                "agent_type": "validator",
                "model": "sonnet",
                "input_tokens": 1000,
                "output_tokens": 100,
                "cost_usd": 0.02,
                "duration_s": 8.0,
                "tool_calls_json": None,
            },
        ],
    )

    reader = CostLogReader(db_path=str(db_path))
    result = reader.load_all()

    assert result.has_data is True
    assert len(result.cost_by_item) == 1
    item = result.cost_by_item[0]
    assert item.item_slug == FIXTURE_ITEM_SLUG
    assert item.item_type == FIXTURE_ITEM_TYPE
    assert item.num_tasks == 2
    assert "coder" in item.agent_types
    assert "validator" in item.agent_types
    assert abs(item.cost_usd - 0.07) < 1e-9
    assert result.cost_by_agent["coder"] == 2000 + 500
    assert result.cost_by_agent["validator"] == 1000 + 100


def test_load_all_db_tool_calls_json_deserialised(tmp_path):
    """tool_calls_json column is deserialised so Read bytes are accumulated."""
    db_path = tmp_path / "test.db"
    tool_calls = [{"tool": "Read", "file_path": "src/foo.py", "result_bytes": 4096}]
    _create_db_with_tasks(
        db_path,
        [
            {
                "item_slug": FIXTURE_ITEM_SLUG,
                "item_type": FIXTURE_ITEM_TYPE,
                "task_id": "1.1",
                "agent_type": "coder",
                "model": "sonnet",
                "input_tokens": 500,
                "output_tokens": 100,
                "cost_usd": 0.01,
                "duration_s": 5.0,
                "tool_calls_json": json.dumps(tool_calls),
            }
        ],
    )

    reader = CostLogReader(db_path=str(db_path))
    result = reader.load_all()

    assert result.has_data is True
    top_files_dict = dict(result.top_files)
    assert "src/foo.py" in top_files_dict
    assert top_files_dict["src/foo.py"] == 4096


def test_load_all_db_missing_falls_back_to_json(tmp_path):
    """When the DB does not exist, load_all() falls back to JSON files."""
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    tasks = [_make_task("1.1", agent_type="coder", cost_usd=0.03)]
    _write_log(logs_dir, f"{FIXTURE_ITEM_SLUG}.json", _make_log(FIXTURE_ITEM_SLUG, FIXTURE_ITEM_TYPE, tasks))

    reader = CostLogReader(logs_dir=logs_dir, db_path=str(tmp_path / "nonexistent.db"))
    result = reader.load_all()

    assert result.has_data is True
    assert len(result.cost_by_item) == 1
    assert result.cost_by_item[0].item_slug == FIXTURE_ITEM_SLUG


def test_load_all_db_no_cost_tasks_table_falls_back_to_json(tmp_path):
    """When DB exists but has no cost_tasks table, load_all() falls back to JSON."""
    db_path = tmp_path / "no-cost-table.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE other_table (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    tasks = [_make_task("1.1", agent_type="coder", cost_usd=0.03)]
    _write_log(logs_dir, f"{FIXTURE_ITEM_SLUG}.json", _make_log(FIXTURE_ITEM_SLUG, FIXTURE_ITEM_TYPE, tasks))

    reader = CostLogReader(logs_dir=logs_dir, db_path=str(db_path))
    result = reader.load_all()

    assert result.has_data is True
    assert result.cost_by_item[0].item_slug == FIXTURE_ITEM_SLUG


def test_load_all_db_empty_table_returns_no_data(tmp_path):
    """When cost_tasks table exists but is empty, has_data is False (no JSON fallback)."""
    db_path = tmp_path / "empty-costs.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE cost_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_slug TEXT NOT NULL, item_type TEXT NOT NULL,
            task_id TEXT NOT NULL, agent_type TEXT NOT NULL,
            model TEXT NOT NULL, input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0, cost_usd REAL NOT NULL DEFAULT 0.0,
            duration_s REAL NOT NULL DEFAULT 0.0, tool_calls_json TEXT,
            recorded_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()

    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    tasks = [_make_task("1.1")]
    _write_log(logs_dir, f"{FIXTURE_ITEM_SLUG}.json", _make_log(FIXTURE_ITEM_SLUG, FIXTURE_ITEM_TYPE, tasks))

    reader = CostLogReader(logs_dir=logs_dir, db_path=str(db_path))
    result = reader.load_all()

    assert result.has_data is False


# ─── svg_bar_chart() tests ────────────────────────────────────────────────────


def test_svg_bar_chart_returns_svg_string():
    """svg_bar_chart() with valid data returns a string starting with '<svg'."""
    result = svg_bar_chart(
        labels=["src/a.py", "src/b.py"],
        values=[5.50, 2.00],
        width=700,
        bar_height=18,
        title="Test Chart",
    )
    assert result.startswith("<svg")
    assert "$5.50" in result
    assert "$2.00" in result


def test_svg_bar_chart_empty_data_returns_svg():
    """svg_bar_chart() with no data still returns an SVG string."""
    result = svg_bar_chart(labels=[], values=[], width=700, bar_height=18, title="Empty")
    assert result.startswith("<svg")


def test_svg_bar_chart_max_bar_value_label_within_viewport():
    """Max-value bar's label starts within the SVG viewport (no clipping).

    With width=700, SVG_BAR_LABEL_PADDING=160, SVG_VALUE_LABEL_PADDING=80:
    bar_area_width = 700 - 160 - 80 = 460. Max bar fills 460px.
    Value label x = 160 + 460 + 5 = 625 < 700, leaving 75px for the text.
    """
    from langgraph_pipeline.web.cost_log_reader import (
        SVG_BAR_LABEL_PADDING,
        SVG_TEXT_OFFSET_X,
        SVG_VALUE_LABEL_PADDING,
    )

    chart_width = 700
    result = svg_bar_chart(
        labels=["node/type/expensive", "node/type/cheap"],
        values=[55.605055300000004, 1.23],
        width=chart_width,
        bar_height=18,
        title="Total Cost by Node Type (USD)",
    )
    assert "$55.61" in result
    assert "$1.23" in result

    bar_area_width = chart_width - SVG_BAR_LABEL_PADDING - SVG_VALUE_LABEL_PADDING
    max_label_x = SVG_BAR_LABEL_PADDING + bar_area_width + SVG_TEXT_OFFSET_X
    assert max_label_x < chart_width, (
        f"Value label x={max_label_x} is outside SVG width={chart_width}"
    )


# ─── /analysis endpoint integration tests ─────────────────────────────────────


@pytest.fixture()
def client_no_proxy():
    """TestClient with proxy disabled (get_proxy returns None) for /analysis."""
    from unittest.mock import patch

    from langgraph_pipeline.web.server import create_app

    app = create_app(config={})
    with patch("langgraph_pipeline.web.routes.analysis.get_proxy", return_value=None):
        yield TestClient(app)


@pytest.fixture()
def client_with_proxy(tmp_path):
    """TestClient with a real TracingProxy backed by a temporary SQLite DB."""
    from unittest.mock import MagicMock, patch

    from langgraph_pipeline.web.proxy import CostSummary, NodeCost, SlugCost
    from langgraph_pipeline.web.server import create_app

    mock_proxy = MagicMock()
    mock_proxy.get_cost_summary.return_value = CostSummary(
        total_cost_usd=1.23,
        today_cost_usd=0.10,
        week_cost_usd=0.50,
        most_expensive_slug=FIXTURE_ITEM_SLUG,
        most_expensive_slug_cost_usd=0.80,
    )
    mock_proxy.get_cost_by_day.return_value = []
    mock_proxy.list_cost_runs.return_value = ([], 0)
    mock_proxy.get_cost_by_slug.return_value = [
        SlugCost(
            item_slug=FIXTURE_ITEM_SLUG,
            item_type=FIXTURE_ITEM_TYPE,
            total_cost_usd=0.80,
            task_count=3,
            avg_cost_usd=0.27,
        )
    ]
    mock_proxy.get_cost_by_node_type.return_value = [
        NodeCost(node_name="execute_task", task_count=5, total_cost_usd=1.00, avg_cost_usd=0.20)
    ]

    app = create_app(config={})
    with patch("langgraph_pipeline.web.routes.analysis.get_proxy", return_value=mock_proxy):
        yield TestClient(app)


def test_analysis_endpoint_no_proxy(client_no_proxy):
    """GET /analysis with proxy disabled returns 404."""
    response = client_no_proxy.get("/analysis")
    assert response.status_code == 404


def test_analysis_endpoint_with_proxy(client_with_proxy):
    """GET /analysis with proxy returns 200."""
    response = client_with_proxy.get("/analysis")
    assert response.status_code == 200
