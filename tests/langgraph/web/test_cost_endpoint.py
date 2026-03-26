# tests/langgraph/web/test_cost_endpoint.py
# Unit tests for POST /api/cost endpoint and TracingProxy.record_cost_task.
# Design: .claude/plans/.claimed/03-cost-analysis-db-backend.md

"""Unit tests for langgraph_pipeline.web.routes.cost and the record_cost_task
method on TracingProxy. Uses FastAPI TestClient for HTTP-level tests."""

import json

import pytest
from fastapi.testclient import TestClient

import langgraph_pipeline.web.proxy as proxy_module
from langgraph_pipeline.web.proxy import TracingProxy
from langgraph_pipeline.web.server import create_app

# ─── Constants ────────────────────────────────────────────────────────────────

SAMPLE_ITEM_SLUG = "01-some-feature"
SAMPLE_ITEM_TYPE = "feature"
SAMPLE_TASK_ID = "1.1"
SAMPLE_AGENT_TYPE = "coder"
SAMPLE_MODEL = "claude-sonnet-4-6"
SAMPLE_INPUT_TOKENS = 12000
SAMPLE_OUTPUT_TOKENS = 3400
SAMPLE_COST_USD = 0.0124
SAMPLE_DURATION_S = 47.2
SAMPLE_TOOL_CALLS = [
    {"tool": "Read", "file_path": "some/file.py", "result_bytes": 4200},
    {"tool": "Bash", "command": "pytest tests/", "result_bytes": 800},
]

MINIMAL_PAYLOAD = {
    "item_slug": SAMPLE_ITEM_SLUG,
    "item_type": SAMPLE_ITEM_TYPE,
    "task_id": SAMPLE_TASK_ID,
    "agent_type": SAMPLE_AGENT_TYPE,
    "model": SAMPLE_MODEL,
    "input_tokens": SAMPLE_INPUT_TOKENS,
    "output_tokens": SAMPLE_OUTPUT_TOKENS,
    "cost_usd": SAMPLE_COST_USD,
    "duration_s": SAMPLE_DURATION_S,
    "tool_calls": SAMPLE_TOOL_CALLS,
}


# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def proxy(tmp_path):
    """Create a TracingProxy backed by a temp-dir SQLite DB."""
    db_path = str(tmp_path / "test-traces.db")
    return TracingProxy({"db_path": db_path, "forward_to_langsmith": False})


@pytest.fixture()
def client(tmp_path, proxy):
    """FastAPI TestClient with proxy singleton wired to the test DB."""
    old = proxy_module._proxy_instance
    proxy_module._proxy_instance = proxy
    app = create_app(config={
        "web": {"proxy": {"db_path": str(tmp_path / "test-traces.db")}},
    })
    # Restore our fixture proxy after create_app replaces the singleton
    proxy_module._proxy_instance = proxy
    yield TestClient(app)
    proxy_module._proxy_instance = old


# ─── TracingProxy.record_cost_task Tests ──────────────────────────────────────


def test_record_cost_task_inserts_row(proxy):
    """record_cost_task() persists a row to cost_tasks that can be read back."""
    proxy.record_cost_task(
        item_slug=SAMPLE_ITEM_SLUG,
        item_type=SAMPLE_ITEM_TYPE,
        task_id=SAMPLE_TASK_ID,
        agent_type=SAMPLE_AGENT_TYPE,
        model=SAMPLE_MODEL,
        input_tokens=SAMPLE_INPUT_TOKENS,
        output_tokens=SAMPLE_OUTPUT_TOKENS,
        cost_usd=SAMPLE_COST_USD,
        duration_s=SAMPLE_DURATION_S,
        tool_calls_json=json.dumps(SAMPLE_TOOL_CALLS),
        recorded_at="2026-03-26T00:00:00+00:00",
    )

    with proxy._connect() as conn:
        rows = conn.execute("SELECT * FROM cost_tasks").fetchall()

    assert len(rows) == 1
    row = dict(rows[0])
    assert row["item_slug"] == SAMPLE_ITEM_SLUG
    assert row["item_type"] == SAMPLE_ITEM_TYPE
    assert row["task_id"] == SAMPLE_TASK_ID
    assert row["agent_type"] == SAMPLE_AGENT_TYPE
    assert row["model"] == SAMPLE_MODEL
    assert row["input_tokens"] == SAMPLE_INPUT_TOKENS
    assert row["output_tokens"] == SAMPLE_OUTPUT_TOKENS
    assert abs(row["cost_usd"] - SAMPLE_COST_USD) < 1e-9
    assert abs(row["duration_s"] - SAMPLE_DURATION_S) < 1e-6
    assert json.loads(row["tool_calls_json"]) == SAMPLE_TOOL_CALLS


def test_record_cost_task_null_tool_calls(proxy):
    """record_cost_task() accepts None for tool_calls_json."""
    proxy.record_cost_task(
        item_slug=SAMPLE_ITEM_SLUG,
        item_type=SAMPLE_ITEM_TYPE,
        task_id=SAMPLE_TASK_ID,
        agent_type=SAMPLE_AGENT_TYPE,
        model=SAMPLE_MODEL,
        input_tokens=0,
        output_tokens=0,
        cost_usd=0.0,
        duration_s=0.0,
        tool_calls_json=None,
        recorded_at="2026-03-26T00:00:00+00:00",
    )

    with proxy._connect() as conn:
        row = conn.execute("SELECT tool_calls_json FROM cost_tasks").fetchone()

    assert row["tool_calls_json"] is None


def test_record_cost_task_multiple_rows(proxy):
    """Multiple calls insert multiple rows; index on item_slug filters correctly."""
    for i in range(3):
        proxy.record_cost_task(
            item_slug=f"item-{i}",
            item_type="feature",
            task_id=f"1.{i}",
            agent_type="coder",
            model=SAMPLE_MODEL,
            input_tokens=100 * i,
            output_tokens=50 * i,
            cost_usd=0.001 * i,
            duration_s=float(i),
            tool_calls_json=None,
            recorded_at="2026-03-26T00:00:00+00:00",
        )

    with proxy._connect() as conn:
        count = conn.execute("SELECT COUNT(*) FROM cost_tasks").fetchone()[0]
        slug_rows = conn.execute(
            "SELECT * FROM cost_tasks WHERE item_slug = ?", ["item-2"]
        ).fetchall()

    assert count == 3
    assert len(slug_rows) == 1
    assert dict(slug_rows[0])["task_id"] == "1.2"


# ─── POST /api/cost HTTP Tests ────────────────────────────────────────────────


def test_post_cost_returns_202_ok(client):
    """POST /api/cost with full payload returns HTTP 202 and {"ok": true}."""
    response = client.post("/api/cost", json=MINIMAL_PAYLOAD)
    assert response.status_code == 202
    assert response.json() == {"ok": True}


def test_post_cost_stores_row_in_db(client, proxy):
    """POST /api/cost persists the record to cost_tasks in the DB."""
    client.post("/api/cost", json=MINIMAL_PAYLOAD)

    with proxy._connect() as conn:
        rows = conn.execute("SELECT * FROM cost_tasks").fetchall()

    assert len(rows) == 1
    row = dict(rows[0])
    assert row["item_slug"] == SAMPLE_ITEM_SLUG
    assert row["task_id"] == SAMPLE_TASK_ID
    assert row["model"] == SAMPLE_MODEL
    assert json.loads(row["tool_calls_json"]) == SAMPLE_TOOL_CALLS


def test_post_cost_without_tool_calls(client, proxy):
    """POST /api/cost without tool_calls field stores a row with NULL tool_calls_json."""
    payload = {k: v for k, v in MINIMAL_PAYLOAD.items() if k != "tool_calls"}
    response = client.post("/api/cost", json=payload)
    assert response.status_code == 202

    with proxy._connect() as conn:
        row = conn.execute("SELECT tool_calls_json FROM cost_tasks").fetchone()
    assert row["tool_calls_json"] is None


def test_post_cost_missing_required_field_returns_422(client):
    """POST /api/cost with a missing required field returns HTTP 422."""
    incomplete = {k: v for k, v in MINIMAL_PAYLOAD.items() if k != "item_slug"}
    response = client.post("/api/cost", json=incomplete)
    assert response.status_code == 422


def test_post_cost_no_proxy_returns_202(tmp_path):
    """POST /api/cost returns 202 even when the proxy singleton is None."""
    old = proxy_module._proxy_instance
    proxy_module._proxy_instance = None
    try:
        app = create_app(config={})
        proxy_module._proxy_instance = None  # override init_proxy result
        with TestClient(app) as client:
            response = client.post("/api/cost", json=MINIMAL_PAYLOAD)
        assert response.status_code == 202
        assert response.json() == {"ok": True}
    finally:
        proxy_module._proxy_instance = old
