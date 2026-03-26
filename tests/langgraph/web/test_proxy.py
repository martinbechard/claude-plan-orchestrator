# tests/langgraph/web/test_proxy.py
# Unit tests for TracingProxy (SQLite persistence) and /proxy FastAPI endpoints.
# Design: docs/plans/2026-03-25-14-langsmith-tracing-proxy-design.md

"""Unit tests for langgraph_pipeline.web.proxy and langgraph_pipeline.web.routes.proxy."""

import json
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
SAMPLE_MODEL = "claude-opus-4-5"
SAMPLE_MULTIPART_BOUNDARY = "testboundary99"


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



# ─── propagate_model_to_root Tests ───────────────────────────────────────────


def test_propagate_model_to_root_sets_model(proxy):
    """propagate_model_to_root updates the root run's model column."""
    proxy.record_run(
        run_id=SAMPLE_PARENT_RUN_ID,
        parent_run_id=None,
        name="root-run",
        inputs=None,
        outputs=None,
        metadata=None,
        error=None,
        start_time=SAMPLE_START_TIME,
        end_time=SAMPLE_END_TIME,
    )
    proxy.record_run(
        run_id=SAMPLE_CHILD_RUN_ID_A,
        parent_run_id=SAMPLE_PARENT_RUN_ID,
        name="child-llm",
        inputs=None,
        outputs=None,
        metadata=None,
        error=None,
        start_time=SAMPLE_START_TIME,
        end_time=SAMPLE_END_TIME,
    )

    proxy.propagate_model_to_root(SAMPLE_CHILD_RUN_ID_A, SAMPLE_MODEL)

    root = proxy.get_run(SAMPLE_PARENT_RUN_ID)
    assert root is not None
    assert root["model"] == SAMPLE_MODEL


def test_propagate_model_to_root_first_write_wins(proxy):
    """A second propagation call does not overwrite the model already set."""
    proxy.record_run(
        run_id=SAMPLE_PARENT_RUN_ID,
        parent_run_id=None,
        name="root-run",
        inputs=None,
        outputs=None,
        metadata=None,
        error=None,
        start_time=SAMPLE_START_TIME,
        end_time=SAMPLE_END_TIME,
    )

    proxy.propagate_model_to_root(SAMPLE_PARENT_RUN_ID, SAMPLE_MODEL)
    proxy.propagate_model_to_root(SAMPLE_PARENT_RUN_ID, "other-model")

    root = proxy.get_run(SAMPLE_PARENT_RUN_ID)
    assert root["model"] == SAMPLE_MODEL


def test_propagate_model_to_root_walks_chain(proxy):
    """propagate_model_to_root walks up a multi-level parent chain to the root."""
    mid_run_id = "run-mid-001"
    proxy.record_run(
        run_id=SAMPLE_PARENT_RUN_ID,
        parent_run_id=None,
        name="root",
        inputs=None,
        outputs=None,
        metadata=None,
        error=None,
        start_time=SAMPLE_START_TIME,
        end_time=SAMPLE_END_TIME,
    )
    proxy.record_run(
        run_id=mid_run_id,
        parent_run_id=SAMPLE_PARENT_RUN_ID,
        name="mid",
        inputs=None,
        outputs=None,
        metadata=None,
        error=None,
        start_time=SAMPLE_START_TIME,
        end_time=SAMPLE_END_TIME,
    )
    proxy.record_run(
        run_id=SAMPLE_CHILD_RUN_ID_A,
        parent_run_id=mid_run_id,
        name="leaf-llm",
        inputs=None,
        outputs=None,
        metadata=None,
        error=None,
        start_time=SAMPLE_START_TIME,
        end_time=SAMPLE_END_TIME,
    )

    proxy.propagate_model_to_root(mid_run_id, SAMPLE_MODEL)

    root = proxy.get_run(SAMPLE_PARENT_RUN_ID)
    assert root["model"] == SAMPLE_MODEL
    mid = proxy.get_run(mid_run_id)
    assert mid["model"] == ""  # Only root is updated


# ─── Trace ID Filter Tests ────────────────────────────────────────────────────


def test_trace_id_filter_list_runs(proxy):
    """list_runs with trace_id= returns only root runs whose run_id starts with the prefix."""
    proxy.record_run(
        run_id="abc-123-match",
        parent_run_id=None,
        name="match-run",
        inputs=None,
        outputs=None,
        metadata=None,
        error=None,
        start_time=SAMPLE_START_TIME,
        end_time=SAMPLE_END_TIME,
    )
    proxy.record_run(
        run_id="xyz-456-other",
        parent_run_id=None,
        name="other-run",
        inputs=None,
        outputs=None,
        metadata=None,
        error=None,
        start_time=SAMPLE_START_TIME,
        end_time=SAMPLE_END_TIME,
    )

    runs = proxy.list_runs(trace_id="abc-123")
    assert len(runs) == 1
    assert runs[0]["run_id"] == "abc-123-match"


def test_trace_id_filter_list_runs_empty_returns_all(proxy):
    """list_runs with trace_id="" returns all root runs (no regression)."""
    for run_id in ("run-a", "run-b"):
        proxy.record_run(
            run_id=run_id,
            parent_run_id=None,
            name=f"name-{run_id}",
            inputs=None,
            outputs=None,
            metadata=None,
            error=None,
            start_time=SAMPLE_START_TIME,
            end_time=SAMPLE_END_TIME,
        )

    runs = proxy.list_runs(trace_id="")
    assert len(runs) == 2


def test_trace_id_filter_count_runs(proxy):
    """count_runs with trace_id= counts only root runs whose run_id starts with the prefix."""
    proxy.record_run(
        run_id="prefix-aaa",
        parent_run_id=None,
        name="run-a",
        inputs=None,
        outputs=None,
        metadata=None,
        error=None,
        start_time=SAMPLE_START_TIME,
        end_time=SAMPLE_END_TIME,
    )
    proxy.record_run(
        run_id="prefix-bbb",
        parent_run_id=None,
        name="run-b",
        inputs=None,
        outputs=None,
        metadata=None,
        error=None,
        start_time=SAMPLE_START_TIME,
        end_time=SAMPLE_END_TIME,
    )
    proxy.record_run(
        run_id="other-ccc",
        parent_run_id=None,
        name="run-c",
        inputs=None,
        outputs=None,
        metadata=None,
        error=None,
        start_time=SAMPLE_START_TIME,
        end_time=SAMPLE_END_TIME,
    )

    assert proxy.count_runs(trace_id="prefix") == 2
    assert proxy.count_runs(trace_id="other") == 1
    assert proxy.count_runs(trace_id="nonexistent") == 0
    assert proxy.count_runs() == 3


# ─── Model Filter Tests ───────────────────────────────────────────────────────


def test_model_filter_list_runs(proxy):
    """list_runs with model= returns only root runs whose model column matches."""
    proxy.record_run(
        run_id="r-match",
        parent_run_id=None,
        name="match-run",
        inputs=None,
        outputs=None,
        metadata=None,
        error=None,
        start_time=SAMPLE_START_TIME,
        end_time=SAMPLE_END_TIME,
    )
    proxy.record_run(
        run_id="r-other",
        parent_run_id=None,
        name="other-run",
        inputs=None,
        outputs=None,
        metadata=None,
        error=None,
        start_time=SAMPLE_START_TIME,
        end_time=SAMPLE_END_TIME,
    )

    proxy.propagate_model_to_root("r-match", SAMPLE_MODEL)

    runs = proxy.list_runs(model="claude-opus")
    assert len(runs) == 1
    assert runs[0]["run_id"] == "r-match"


def test_model_filter_count_runs(proxy):
    """count_runs with model= counts only root runs whose model column matches."""
    proxy.record_run(
        run_id="r-match",
        parent_run_id=None,
        name="match-run",
        inputs=None,
        outputs=None,
        metadata=None,
        error=None,
        start_time=SAMPLE_START_TIME,
        end_time=SAMPLE_END_TIME,
    )
    proxy.record_run(
        run_id="r-other",
        parent_run_id=None,
        name="other-run",
        inputs=None,
        outputs=None,
        metadata=None,
        error=None,
        start_time=SAMPLE_START_TIME,
        end_time=SAMPLE_END_TIME,
    )

    proxy.propagate_model_to_root("r-match", SAMPLE_MODEL)

    assert proxy.count_runs(model="claude-opus") == 1
    assert proxy.count_runs(model="nonexistent") == 0
    assert proxy.count_runs() == 2


# ─── Multipart Model Extraction Tests ────────────────────────────────────────


def _build_multipart_body(run_id: str, parent_run_id: str, model: str) -> bytes:
    """Build a minimal multipart body with model in extra.invocation_params."""
    run_json = json.dumps({"name": "llm-call", "parent_run_id": parent_run_id}).encode()
    extra_json = json.dumps({"invocation_params": {"model": model}}).encode()
    boundary = SAMPLE_MULTIPART_BOUNDARY
    parts = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="post.{run_id}"\r\n'
        f"Content-Type: application/json\r\n\r\n"
    ).encode() + run_json + (
        f"\r\n--{boundary}\r\n"
        f'Content-Disposition: form-data; name="post.{run_id}.extra"\r\n'
        f"Content-Type: application/json\r\n\r\n"
    ).encode() + extra_json + f"\r\n--{boundary}--\r\n".encode()
    return parts


def test_multipart_model_extraction(enabled_client):
    """POST /runs/multipart with invocation_params.model propagates to root run."""
    proxy = get_proxy()
    assert proxy is not None

    root_run_id = "mp-root-001"
    child_run_id = "mp-child-001"

    proxy.record_run(
        run_id=root_run_id,
        parent_run_id=None,
        name="mp-root",
        inputs=None,
        outputs=None,
        metadata=None,
        error=None,
        start_time=SAMPLE_START_TIME,
        end_time=SAMPLE_END_TIME,
    )

    body = _build_multipart_body(child_run_id, root_run_id, SAMPLE_MODEL)
    response = enabled_client.post(
        "/runs/multipart",
        content=body,
        headers={"content-type": f"multipart/form-data; boundary={SAMPLE_MULTIPART_BOUNDARY}"},
    )
    assert response.status_code == 202

    root = proxy.get_run(root_run_id)
    assert root is not None
    assert root["model"] == SAMPLE_MODEL


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
