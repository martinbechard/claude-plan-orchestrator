# tests/langgraph/web/test_sessions_routes.py
# Unit tests for GET /sessions and GET /api/sessions endpoints.
# Design: tmp/plans/.claimed/15-session-tracking-and-cost-history.md

"""Unit tests for langgraph_pipeline.web.routes.sessions.
Uses FastAPI TestClient for HTTP-level verification."""

import pytest
from fastapi.testclient import TestClient

import langgraph_pipeline.web.proxy as proxy_module
from langgraph_pipeline.web.proxy import TracingProxy
from langgraph_pipeline.web.server import create_app

# ─── Constants ────────────────────────────────────────────────────────────────

SAMPLE_START_TIME = "2026-03-27T10:00:00+00:00"
SAMPLE_END_TIME = "2026-03-27T12:00:00+00:00"
SAMPLE_LABEL = "Morning run"
SAMPLE_COST_USD = 1.2345
SAMPLE_ITEMS = 42


# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def proxy(tmp_path):
    """TracingProxy backed by a temp-dir SQLite DB."""
    db_path = str(tmp_path / "test-sessions.db")
    return TracingProxy({"db_path": db_path, "forward_to_langsmith": False})


@pytest.fixture()
def client(tmp_path, proxy):
    """FastAPI TestClient with proxy singleton wired to the test DB."""
    old = proxy_module._proxy_instance
    proxy_module._proxy_instance = proxy
    app = create_app(config={
        "web": {"proxy": {"db_path": str(tmp_path / "test-sessions.db")}},
    })
    proxy_module._proxy_instance = proxy
    yield TestClient(app)
    proxy_module._proxy_instance = old


def _insert_session(proxy: TracingProxy, label: str = SAMPLE_LABEL) -> int:
    """Insert a completed session row directly into the DB and return its id."""
    with proxy._connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO sessions (label, start_time, end_time, total_cost_usd, items_processed, notes)
            VALUES (?, ?, ?, ?, ?, NULL)
            """,
            [label, SAMPLE_START_TIME, SAMPLE_END_TIME, SAMPLE_COST_USD, SAMPLE_ITEMS],
        )
        return cursor.lastrowid


# ─── GET /api/sessions Tests ──────────────────────────────────────────────────


def test_api_sessions_empty_returns_200(client):
    """GET /api/sessions with no data returns 200 with empty lists."""
    response = client.get("/api/sessions")
    assert response.status_code == 200
    data = response.json()
    assert data["sessions"] == []
    assert data["daily_totals"] == []


def test_api_sessions_returns_session_data(client, proxy):
    """GET /api/sessions returns the inserted session in the sessions list."""
    _insert_session(proxy)
    response = client.get("/api/sessions")
    assert response.status_code == 200
    data = response.json()
    assert len(data["sessions"]) == 1
    session = data["sessions"][0]
    assert session["label"] == SAMPLE_LABEL
    assert session["start_time"] == SAMPLE_START_TIME
    assert session["end_time"] == SAMPLE_END_TIME
    assert abs(session["total_cost_usd"] - SAMPLE_COST_USD) < 1e-9
    assert session["items_processed"] == SAMPLE_ITEMS


def test_api_sessions_multiple_sessions_ordered_newest_first(client, proxy):
    """GET /api/sessions returns sessions newest-first."""
    with proxy._connect() as conn:
        conn.execute(
            "INSERT INTO sessions (label, start_time, end_time, total_cost_usd, items_processed, notes) VALUES (?, ?, ?, ?, ?, NULL)",
            ["First run", "2026-03-26T10:00:00+00:00", "2026-03-26T12:00:00+00:00", 0.5, 10],
        )
        conn.execute(
            "INSERT INTO sessions (label, start_time, end_time, total_cost_usd, items_processed, notes) VALUES (?, ?, ?, ?, ?, NULL)",
            ["Second run", "2026-03-27T10:00:00+00:00", "2026-03-27T12:00:00+00:00", 1.0, 20],
        )

    response = client.get("/api/sessions")
    assert response.status_code == 200
    sessions = response.json()["sessions"]
    assert len(sessions) == 2
    assert sessions[0]["label"] == "Second run"
    assert sessions[1]["label"] == "First run"


def test_api_sessions_includes_daily_totals(client, proxy):
    """GET /api/sessions includes daily_totals from completions table."""
    with proxy._connect() as conn:
        conn.execute(
            """
            INSERT INTO completions (slug, item_type, outcome, cost_usd, duration_s, finished_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ["test-item-abc123", "feature", "success", 0.75, 30.0, "2026-03-27T10:00:00+00:00"],
        )

    response = client.get("/api/sessions")
    assert response.status_code == 200
    daily_totals = response.json()["daily_totals"]
    assert len(daily_totals) == 1
    assert daily_totals[0]["date_str"] == "2026-03-27"
    assert abs(daily_totals[0]["cost_usd"] - 0.75) < 1e-9
    assert daily_totals[0]["items_processed"] == 1


def test_api_sessions_no_proxy_returns_404(tmp_path):
    """GET /api/sessions returns 404 when the proxy singleton is None."""
    old = proxy_module._proxy_instance
    proxy_module._proxy_instance = None
    try:
        app = create_app(config={})
        proxy_module._proxy_instance = None
        with TestClient(app) as test_client:
            response = test_client.get("/api/sessions")
        assert response.status_code == 404
    finally:
        proxy_module._proxy_instance = old


# ─── GET /sessions HTML Tests ─────────────────────────────────────────────────


def test_get_sessions_page_returns_200(client):
    """GET /sessions returns HTTP 200 when proxy is enabled."""
    response = client.get("/sessions")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_get_sessions_page_no_proxy_returns_404(tmp_path):
    """GET /sessions returns 404 when the proxy singleton is None."""
    old = proxy_module._proxy_instance
    proxy_module._proxy_instance = None
    try:
        app = create_app(config={})
        proxy_module._proxy_instance = None
        with TestClient(app) as test_client:
            response = test_client.get("/sessions")
        assert response.status_code == 404
    finally:
        proxy_module._proxy_instance = old
