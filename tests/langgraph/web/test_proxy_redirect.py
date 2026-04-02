# tests/langgraph/web/test_proxy_redirect.py
# Unit tests for the GET /proxy redirect endpoint in server.py.
# Design: docs/plans/2026-04-02-01-during-the-execution-of-a-work-item-there-is-a-view-trace-link-in-the-workitem-design.md

"""Tests for the GET /proxy redirect endpoint added in create_app().

Coverage:
- Valid trace_id redirects (302) to /execution-history/{trace_id}
- Missing trace_id returns 400
- Unknown trace_id returns 404 with a descriptive message
- No proxy initialised: redirect proceeds without validation

Note: get_proxy is patched at its definition site (langgraph_pipeline.web.proxy)
because the handler imports it there at call time. The patch must remain active
while the request is in flight, so the with-block always spans the client.get() call.
"""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from langgraph_pipeline.web.server import create_app

# ─── Constants ────────────────────────────────────────────────────────────────

KNOWN_TRACE_ID = "abc-123-trace"
UNKNOWN_TRACE_ID = "no-such-trace"
_PROXY_TARGET = "langgraph_pipeline.web.proxy.get_proxy"

# ─── Tests ────────────────────────────────────────────────────────────────────


class TestProxyRedirectValid:
    """GET /proxy with a known trace_id redirects to /execution-history."""

    def test_returns_302(self):
        """Status code is 302 Found."""
        mock_proxy = MagicMock()
        mock_proxy.get_run.return_value = {"run_id": KNOWN_TRACE_ID}
        with patch(_PROXY_TARGET, return_value=mock_proxy):
            app = create_app(config={})
            client = TestClient(app, follow_redirects=False)
            response = client.get(f"/proxy?trace_id={KNOWN_TRACE_ID}")
        assert response.status_code == 302

    def test_location_header_points_to_execution_history(self):
        """Location header contains /execution-history/{trace_id}."""
        mock_proxy = MagicMock()
        mock_proxy.get_run.return_value = {"run_id": KNOWN_TRACE_ID}
        with patch(_PROXY_TARGET, return_value=mock_proxy):
            app = create_app(config={})
            client = TestClient(app, follow_redirects=False)
            response = client.get(f"/proxy?trace_id={KNOWN_TRACE_ID}")
        assert response.headers["location"].endswith(f"/execution-history/{KNOWN_TRACE_ID}")


class TestProxyRedirectMissingParam:
    """GET /proxy without trace_id returns 400."""

    def test_missing_trace_id_returns_400(self):
        """Omitting trace_id yields HTTP 400."""
        app = create_app(config={})
        client = TestClient(app, follow_redirects=False)
        response = client.get("/proxy")
        assert response.status_code == 400

    def test_empty_trace_id_returns_400(self):
        """An empty trace_id string yields HTTP 400."""
        app = create_app(config={})
        client = TestClient(app, follow_redirects=False)
        response = client.get("/proxy?trace_id=")
        assert response.status_code == 400

    def test_missing_trace_id_error_message(self):
        """Error detail mentions trace_id."""
        app = create_app(config={})
        client = TestClient(app, follow_redirects=False)
        response = client.get("/proxy")
        body = response.json()
        assert "trace_id" in body.get("detail", "").lower()


class TestProxyRedirectUnknownTrace:
    """GET /proxy with an unknown trace_id returns 404."""

    def test_unknown_trace_returns_404(self):
        """get_run returning None yields HTTP 404."""
        mock_proxy = MagicMock()
        mock_proxy.get_run.return_value = None
        with patch(_PROXY_TARGET, return_value=mock_proxy):
            app = create_app(config={})
            client = TestClient(app, follow_redirects=False)
            response = client.get(f"/proxy?trace_id={UNKNOWN_TRACE_ID}")
        assert response.status_code == 404

    def test_unknown_trace_error_contains_trace_id(self):
        """The 404 detail references the requested trace_id."""
        mock_proxy = MagicMock()
        mock_proxy.get_run.return_value = None
        with patch(_PROXY_TARGET, return_value=mock_proxy):
            app = create_app(config={})
            client = TestClient(app, follow_redirects=False)
            response = client.get(f"/proxy?trace_id={UNKNOWN_TRACE_ID}")
        body = response.json()
        assert UNKNOWN_TRACE_ID in body.get("detail", "")


class TestProxyRedirectNoProxy:
    """GET /proxy when proxy is not initialised still redirects."""

    def test_redirect_when_proxy_is_none(self):
        """When get_proxy() returns None, the endpoint still redirects (302)."""
        with patch(_PROXY_TARGET, return_value=None):
            app = create_app(config={})
            client = TestClient(app, follow_redirects=False)
            response = client.get(f"/proxy?trace_id={KNOWN_TRACE_ID}")
        assert response.status_code == 302
        assert response.headers["location"].endswith(f"/execution-history/{KNOWN_TRACE_ID}")
