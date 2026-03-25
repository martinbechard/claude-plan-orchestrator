# tests/langgraph/web/test_dashboard_routes.py
# Integration tests for the /dashboard HTML page and /api/stream SSE endpoint.
# Design: docs/plans/2026-03-25-15-pipeline-activity-dashboard-design.md

"""Integration tests for langgraph_pipeline.web.routes.dashboard."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from langgraph_pipeline.web.dashboard_state import reset_dashboard_state
from langgraph_pipeline.web.server import create_app

# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def fresh_state():
    """Reset the dashboard singleton before every test."""
    reset_dashboard_state()
    yield
    reset_dashboard_state()


@pytest.fixture()
def client():
    """FastAPI TestClient with default (no-proxy) configuration."""
    app = create_app(config={})
    return TestClient(app)


# ─── Route Tests ──────────────────────────────────────────────────────────────


def test_dashboard_html_returns_200(client):
    """GET /dashboard returns 200 with HTML content."""
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


@pytest.mark.asyncio
async def test_stream_sends_state_event():
    """The SSE generator yields at least one 'event: state' message.

    Tests _state_event_generator directly with a mocked request to avoid
    the infinite-stream hang that TestClient produces with SSE endpoints.
    asyncio.sleep is patched so the test completes instantly.
    """
    from langgraph_pipeline.web.routes.dashboard import _state_event_generator

    mock_request = AsyncMock()
    # First call: not disconnected (allows one iteration); second: disconnected.
    mock_request.is_disconnected.side_effect = [False, True]

    with patch("langgraph_pipeline.web.routes.dashboard.asyncio.sleep"):
        events = []
        async for chunk in _state_event_generator(mock_request):
            events.append(chunk)

    assert len(events) >= 1
    assert events[0].startswith("event: state")
