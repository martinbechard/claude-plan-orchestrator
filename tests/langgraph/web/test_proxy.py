# tests/langgraph/web/test_proxy.py
# Unit tests for TracingProxy (SQLite persistence) and /proxy FastAPI endpoints.
# Design: docs/plans/2026-03-25-14-langsmith-tracing-proxy-design.md

"""Unit tests for langgraph_pipeline.web.proxy and langgraph_pipeline.web.routes.proxy."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import langgraph_pipeline.web.proxy as proxy_module
from langgraph_pipeline.web.proxy import TracingProxy, get_proxy, init_proxy
from langgraph_pipeline.web.server import create_app

# ─── Constants ────────────────────────────────────────────────────────────────

SAMPLE_RUN_ID = "run-abc-123"
SAMPLE_PARENT_RUN_ID = "run-parent-001"
SAMPLE_CHILD_RUN_ID_A = "run-child-a"
SAMPLE_CHILD_RUN_ID_B = "run-child-b"
SAMPLE_RUN_NAME = "test-tool-call"
SAMPLE_START_TIME = "2026-03-25T10:00:00"
SAMPLE_END_TIME = "2026-03-25T10:00:05"
SAMPLE_INPUTS = {"prompt": "hello"}
SAMPLE_OUTPUTS = {"result": "world"}
SAMPLE_METADATA = {"model": "claude-opus", "slug": "item-42"}


# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def proxy(tmp_path):
    """Create a TracingProxy backed by a temp-dir SQLite DB."""
    db_path = str(tmp_path / "test-traces.db")
    config = {"db_path": db_path, "forward_to_langsmith": False}
    return TracingProxy(config)


@pytest.fixture()
def _set_proxy_singleton(proxy):
    """Install the test proxy as the module-level singleton and reset after."""
    old = proxy_module._proxy_instance
    proxy_module._proxy_instance = proxy
    yield
    proxy_module._proxy_instance = old


@pytest.fixture()
def enabled_client(tmp_path, _set_proxy_singleton):
    """FastAPI TestClient with the proxy enabled and singleton wired."""
    app = create_app(config={
        "web": {"proxy": {
            "enabled": True,
            "db_path": str(tmp_path / "test-traces.db"),
        }},
    })
    # Override the newly-created singleton with our fixture proxy
    # (create_app calls init_proxy which replaces the singleton)
    return TestClient(app)


@pytest.fixture()
def disabled_client():
    """FastAPI TestClient with the proxy disabled."""
    old = proxy_module._proxy_instance
    proxy_module._proxy_instance = None
    app = create_app(config={"web": {"proxy": {"enabled": False}}})
    yield TestClient(app)
    proxy_module._proxy_instance = old


# ─── TracingProxy DB Tests ────────────────────────────────────────────────────


def test_proxy_db_write_and_read(proxy):
    """Write a run via record_run(), then read it back with list_runs() and get_run()."""
    proxy.record_run(
        run_id=SAMPLE_RUN_ID,
        parent_run_id=None,
        name=SAMPLE_RUN_NAME,
        inputs=SAMPLE_INPUTS,
        outputs=SAMPLE_OUTPUTS,
        metadata=SAMPLE_METADATA,
        error=None,
        start_time=SAMPLE_START_TIME,
        end_time=SAMPLE_END_TIME,
    )

    # list_runs returns root runs (parent_run_id IS NULL)
    runs = proxy.list_runs(page=1)
    assert len(runs) == 1
    row = runs[0]
    assert row["run_id"] == SAMPLE_RUN_ID
    assert row["name"] == SAMPLE_RUN_NAME
    assert row["start_time"] == SAMPLE_START_TIME
    assert row["end_time"] == SAMPLE_END_TIME

    # get_run returns the same row
    single = proxy.get_run(SAMPLE_RUN_ID)
    assert single is not None
    assert single["run_id"] == SAMPLE_RUN_ID
    assert single["name"] == SAMPLE_RUN_NAME

    # Verify JSON fields were serialised and can be read back
    assert '"prompt"' in single["inputs_json"]
    assert '"result"' in single["outputs_json"]
    assert '"claude-opus"' in single["metadata_json"]


def test_proxy_get_children(proxy):
    """Write a parent + two children, verify get_children returns both."""
    proxy.record_run(
        run_id=SAMPLE_PARENT_RUN_ID,
        parent_run_id=None,
        name="parent-run",
        inputs=None,
        outputs=None,
        metadata=None,
        error=None,
        start_time=SAMPLE_START_TIME,
        end_time=SAMPLE_END_TIME,
    )
    for child_id, child_name in [
        (SAMPLE_CHILD_RUN_ID_A, "child-a"),
        (SAMPLE_CHILD_RUN_ID_B, "child-b"),
    ]:
        proxy.record_run(
            run_id=child_id,
            parent_run_id=SAMPLE_PARENT_RUN_ID,
            name=child_name,
            inputs=None,
            outputs=None,
            metadata=None,
            error=None,
            start_time=SAMPLE_START_TIME,
            end_time=SAMPLE_END_TIME,
        )

    children = proxy.get_children(SAMPLE_PARENT_RUN_ID)
    assert len(children) == 2
    child_ids = {c["run_id"] for c in children}
    assert child_ids == {SAMPLE_CHILD_RUN_ID_A, SAMPLE_CHILD_RUN_ID_B}


# ─── FastAPI Endpoint Tests ──────────────────────────────────────────────────


def test_proxy_list_endpoint(enabled_client):
    """GET /proxy returns 200 and contains the run name in the HTML."""
    proxy = get_proxy()
    assert proxy is not None
    proxy.record_run(
        run_id=SAMPLE_RUN_ID,
        parent_run_id=None,
        name=SAMPLE_RUN_NAME,
        inputs=SAMPLE_INPUTS,
        outputs=SAMPLE_OUTPUTS,
        metadata=SAMPLE_METADATA,
        error=None,
        start_time=SAMPLE_START_TIME,
        end_time=SAMPLE_END_TIME,
    )

    response = enabled_client.get("/proxy")
    assert response.status_code == 200
    assert SAMPLE_RUN_NAME in response.text


def test_proxy_detail_endpoint(enabled_client):
    """GET /proxy/{run_id} returns 200 and contains an SVG element."""
    proxy = get_proxy()
    assert proxy is not None
    # Write parent run
    proxy.record_run(
        run_id=SAMPLE_RUN_ID,
        parent_run_id=None,
        name=SAMPLE_RUN_NAME,
        inputs=SAMPLE_INPUTS,
        outputs=SAMPLE_OUTPUTS,
        metadata=SAMPLE_METADATA,
        error=None,
        start_time=SAMPLE_START_TIME,
        end_time=SAMPLE_END_TIME,
    )
    # Write a child run so the Gantt chart renders bars
    proxy.record_run(
        run_id=SAMPLE_CHILD_RUN_ID_A,
        parent_run_id=SAMPLE_RUN_ID,
        name="child-tool",
        inputs=None,
        outputs=None,
        metadata=None,
        error=None,
        start_time=SAMPLE_START_TIME,
        end_time=SAMPLE_END_TIME,
    )

    response = enabled_client.get(f"/proxy/{SAMPLE_RUN_ID}")
    assert response.status_code == 200
    assert "<svg" in response.text


def test_proxy_disabled_returns_404(disabled_client):
    """When proxy is disabled, both /proxy and /proxy/{id} return 404."""
    response = disabled_client.get("/proxy")
    assert response.status_code == 404

    response = disabled_client.get(f"/proxy/{SAMPLE_RUN_ID}")
    assert response.status_code == 404


# ─── Error Resilience ────────────────────────────────────────────────────────


def test_proxy_forward_failure_does_not_raise(tmp_path):
    """Even when _forward_async raises, record_run() completes without exception."""
    db_path = str(tmp_path / "fwd-fail.db")
    config = {"db_path": db_path, "forward_to_langsmith": True}
    p = TracingProxy(config)

    with patch.object(p, "_forward_async", side_effect=RuntimeError("boom")):
        # record_run catches the error internally — should not propagate
        p.record_run(
            run_id=SAMPLE_RUN_ID,
            parent_run_id=None,
            name=SAMPLE_RUN_NAME,
            inputs=SAMPLE_INPUTS,
            outputs=SAMPLE_OUTPUTS,
            metadata=SAMPLE_METADATA,
            error=None,
            start_time=SAMPLE_START_TIME,
            end_time=SAMPLE_END_TIME,
        )

    # Verify the row was still written despite the forward failure
    row = p.get_run(SAMPLE_RUN_ID)
    assert row is not None
    assert row["name"] == SAMPLE_RUN_NAME
