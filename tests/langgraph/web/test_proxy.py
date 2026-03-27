# tests/langgraph/web/test_proxy.py
# Unit tests for TracingProxy (SQLite persistence) and /proxy FastAPI endpoints.
# Design: docs/plans/2026-03-25-14-langsmith-tracing-proxy-design.md
# Design: docs/plans/2026-03-26-16-tool-calls-missing-from-traces-design.md

"""Unit tests for langgraph_pipeline.web.proxy and langgraph_pipeline.web.routes.proxy."""

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import langgraph_pipeline.web.proxy as proxy_module
from langgraph_pipeline.web.proxy import TracingProxy, get_proxy, init_proxy
from langgraph_pipeline.web.routes.proxy import _compute_elapsed, _parse_iso
from langgraph_pipeline.web.server import create_app

# ─── Constants ────────────────────────────────────────────────────────────────

SAMPLE_RUN_ID = "run-abc-123"
SAMPLE_PARENT_RUN_ID = "run-parent-001"
SAMPLE_CHILD_RUN_ID_A = "run-child-a"
SAMPLE_CHILD_RUN_ID_B = "run-child-b"
SAMPLE_GRANDCHILD_RUN_ID = "run-grandchild-a"
SAMPLE_RUN_NAME = "test-tool-call"
SAMPLE_GRANDCHILD_NAME = "Read"
SAMPLE_START_TIME = "2026-03-25T10:00:00"
SAMPLE_END_TIME = "2026-03-25T10:00:05"
SAMPLE_GRANDCHILD_END_TIME = "2026-03-25T10:00:10"
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

TRACE_UUID = "a1b2c3d4-0000-0000-0000-000000000001"
TRACE_CHILD_A = "a1b2c3d4-0000-0000-0000-000000000002"
TRACE_CHILD_B = "a1b2c3d4-0000-0000-0000-000000000003"
TRACE_OTHER_UUID = "ffffffff-0000-0000-0000-000000000099"


def test_trace_id_filter_list_runs_returns_root_and_children(proxy):
    """list_runs with trace_id= returns the exact root run and its direct children."""
    proxy.record_run(
        run_id=TRACE_UUID,
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
        run_id=TRACE_CHILD_A,
        parent_run_id=TRACE_UUID,
        name="child-a",
        inputs=None,
        outputs=None,
        metadata=None,
        error=None,
        start_time=SAMPLE_START_TIME,
        end_time=SAMPLE_END_TIME,
    )
    proxy.record_run(
        run_id=TRACE_OTHER_UUID,
        parent_run_id=None,
        name="other-root",
        inputs=None,
        outputs=None,
        metadata=None,
        error=None,
        start_time=SAMPLE_START_TIME,
        end_time=SAMPLE_END_TIME,
    )

    runs = proxy.list_runs(trace_id=TRACE_UUID)
    run_ids = {r["run_id"] for r in runs}
    assert run_ids == {TRACE_UUID, TRACE_CHILD_A}
    assert TRACE_OTHER_UUID not in run_ids


def test_trace_id_filter_list_runs_child_only_visible_before_root(proxy):
    """list_runs with trace_id= finds children even when root run is not yet in DB."""
    proxy.record_run(
        run_id=TRACE_CHILD_A,
        parent_run_id=TRACE_UUID,
        name="in-flight-child",
        inputs=None,
        outputs=None,
        metadata=None,
        error=None,
        start_time=SAMPLE_START_TIME,
        end_time=SAMPLE_END_TIME,
    )
    proxy.record_run(
        run_id=TRACE_CHILD_B,
        parent_run_id=TRACE_UUID,
        name="in-flight-child-b",
        inputs=None,
        outputs=None,
        metadata=None,
        error=None,
        start_time=SAMPLE_START_TIME,
        end_time=SAMPLE_END_TIME,
    )

    runs = proxy.list_runs(trace_id=TRACE_UUID)
    run_ids = {r["run_id"] for r in runs}
    assert run_ids == {TRACE_CHILD_A, TRACE_CHILD_B}


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
    """count_runs with trace_id= counts root and direct children; no trace_id counts roots only."""
    proxy.record_run(
        run_id=TRACE_UUID,
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
        run_id=TRACE_CHILD_A,
        parent_run_id=TRACE_UUID,
        name="child-a",
        inputs=None,
        outputs=None,
        metadata=None,
        error=None,
        start_time=SAMPLE_START_TIME,
        end_time=SAMPLE_END_TIME,
    )
    proxy.record_run(
        run_id=TRACE_CHILD_B,
        parent_run_id=TRACE_UUID,
        name="child-b",
        inputs=None,
        outputs=None,
        metadata=None,
        error=None,
        start_time=SAMPLE_START_TIME,
        end_time=SAMPLE_END_TIME,
    )
    proxy.record_run(
        run_id=TRACE_OTHER_UUID,
        parent_run_id=None,
        name="other-root",
        inputs=None,
        outputs=None,
        metadata=None,
        error=None,
        start_time=SAMPLE_START_TIME,
        end_time=SAMPLE_END_TIME,
    )

    assert proxy.count_runs(trace_id=TRACE_UUID) == 3  # root + 2 children
    assert proxy.count_runs(trace_id=TRACE_OTHER_UUID) == 1  # root only
    assert proxy.count_runs(trace_id="nonexistent-uuid") == 0
    assert proxy.count_runs() == 2  # only root runs: TRACE_UUID and TRACE_OTHER_UUID


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


# ─── Duplicate-run Deduplication Tests ───────────────────────────────────────


def test_duplicate_record_run_inserts_only_one_row(proxy):
    """Calling record_run twice with the same run_id inserts only one DB row."""
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
    # Second call with same run_id (simulating duplicate LangChain callback)
    proxy.record_run(
        run_id=SAMPLE_RUN_ID,
        parent_run_id=None,
        name=SAMPLE_RUN_NAME,
        inputs={"prompt": "different"},
        outputs={"result": "ignored"},
        metadata=SAMPLE_METADATA,
        error=None,
        start_time="2026-03-25T11:00:00",
        end_time="2026-03-25T11:00:05",
    )

    runs = proxy.list_runs(page=1)
    assert len(runs) == 1
    assert runs[0]["run_id"] == SAMPLE_RUN_ID
    # Upsert preserves inputs_json from the first write; only end_time/outputs_json/error are updated
    row = proxy.get_run(SAMPLE_RUN_ID)
    assert '"prompt": "hello"' in row["inputs_json"]


def test_list_root_traces_by_slug_deduplicates_pre_existing_rows(proxy):
    """list_root_traces_by_slug returns one row per run_id even with duplicate DB rows.

    This covers databases that had duplicate rows before the UNIQUE index was added:
    we bypass record_run by writing two rows with the same run_id directly,
    then verify the query collapses them to a single result.
    """
    slug = "item-99"
    run_id = "run-dup-slug-001"
    # Bypass record_run by writing directly to SQLite after dropping the unique index
    with proxy._connect() as conn:
        conn.execute(
            "INSERT INTO traces (run_id, parent_run_id, name, created_at) VALUES (?, NULL, ?, ?)",
            (run_id, f"pipeline-{slug}-first", "2026-03-25T09:00:00"),
        )
        # Drop the unique index so we can insert a true duplicate for the test
        conn.execute("DROP INDEX IF EXISTS idx_traces_run_id_unique")
        conn.execute(
            "INSERT INTO traces (run_id, parent_run_id, name, created_at) VALUES (?, NULL, ?, ?)",
            (run_id, f"pipeline-{slug}-second", "2026-03-25T10:00:00"),
        )

    results = proxy.list_root_traces_by_slug(slug)
    assert len(results) == 1
    assert results[0]["run_id"] == run_id
    # MIN(created_at) should return the earlier timestamp
    assert results[0]["created_at"] == "2026-03-25T09:00:00"


def test_upsert_merges_start_and_completion_events(proxy):
    """record_run with the same run_id merges completion data into the start-event row.

    The start event arrives first (no outputs, no end_time). The completion event
    arrives second (with outputs and end_time). The upsert must update end_time,
    outputs_json, and error while preserving inputs_json from the start event.
    """
    # Start event: has inputs but no outputs or end_time
    proxy.record_run(
        run_id=SAMPLE_RUN_ID,
        parent_run_id=None,
        name=SAMPLE_RUN_NAME,
        inputs=SAMPLE_INPUTS,
        outputs=None,
        metadata=SAMPLE_METADATA,
        error=None,
        start_time=SAMPLE_START_TIME,
        end_time=None,
    )
    # Completion event: has outputs and end_time
    proxy.record_run(
        run_id=SAMPLE_RUN_ID,
        parent_run_id=None,
        name=SAMPLE_RUN_NAME,
        inputs=None,
        outputs=SAMPLE_OUTPUTS,
        metadata=SAMPLE_METADATA,
        error=None,
        start_time=SAMPLE_START_TIME,
        end_time=SAMPLE_END_TIME,
    )

    runs = proxy.list_runs(page=1)
    assert len(runs) == 1

    row = proxy.get_run(SAMPLE_RUN_ID)
    assert row is not None
    # inputs_json preserved from start event
    assert '"prompt"' in row["inputs_json"]
    # outputs_json updated from completion event
    assert '"result"' in row["outputs_json"]
    # end_time updated from completion event
    assert row["end_time"] == SAMPLE_END_TIME


def test_init_db_deduplicates_pre_existing_duplicate_run_ids(tmp_path):
    """_init_db removes pre-existing duplicate run_id rows on startup.

    Simulates a database that accumulated duplicates before the unique index
    existed. The deduplication in _init_db must clean them up so that
    CREATE UNIQUE INDEX succeeds without an IntegrityError.
    """
    import sqlite3 as _sqlite3

    db_path = str(tmp_path / "dup-traces.db")
    run_id = "run-preexisting-dup"

    # Seed the DB with duplicate rows directly (no unique index yet)
    conn = _sqlite3.connect(db_path)
    conn.execute(
        """CREATE TABLE traces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            parent_run_id TEXT,
            name TEXT NOT NULL,
            model TEXT NOT NULL DEFAULT '',
            start_time TEXT, end_time TEXT,
            inputs_json TEXT, outputs_json TEXT, metadata_json TEXT,
            error TEXT, created_at TEXT NOT NULL
        )"""
    )
    conn.execute(
        "INSERT INTO traces (run_id, name, created_at) VALUES (?, ?, ?)",
        (run_id, "start-event", "2026-03-25T09:00:00"),
    )
    conn.execute(
        "INSERT INTO traces (run_id, name, created_at) VALUES (?, ?, ?)",
        (run_id, "completion-event", "2026-03-25T09:00:05"),
    )
    conn.commit()
    conn.close()

    # Creating TracingProxy against this DB triggers _init_db which must deduplicate
    config = {"db_path": db_path, "forward_to_langsmith": False}
    p = TracingProxy(config)

    # Only one row should remain (the one with MAX(id), i.e. the completion event)
    row = p.get_run(run_id)
    assert row is not None
    assert row["name"] == "completion-event"

    # The unique index must now exist and enforce uniqueness
    p.record_run(
        run_id=run_id,
        parent_run_id=None,
        name="updated-name",
        inputs=None,
        outputs=None,
        metadata=None,
        error=None,
        start_time=None,
        end_time=None,
    )
    rows = p.list_runs(page=1)
    assert len(rows) == 1


# ─── get_children_batch Tests ────────────────────────────────────────────────


def test_get_children_batch_returns_grouped_children(proxy):
    """get_children_batch returns children grouped by parent_run_id."""
    child_id_b2 = "run-child-b2"
    for run_id, parent_id, name in [
        (SAMPLE_PARENT_RUN_ID, None, "root"),
        (SAMPLE_CHILD_RUN_ID_A, SAMPLE_PARENT_RUN_ID, "child-a"),
        (SAMPLE_CHILD_RUN_ID_B, SAMPLE_PARENT_RUN_ID, "child-b"),
        (SAMPLE_GRANDCHILD_RUN_ID, SAMPLE_CHILD_RUN_ID_A, "grandchild-a1"),
        (child_id_b2, SAMPLE_CHILD_RUN_ID_A, "grandchild-a2"),
    ]:
        proxy.record_run(
            run_id=run_id,
            parent_run_id=parent_id,
            name=name,
            inputs=None,
            outputs=None,
            metadata=None,
            error=None,
            start_time=SAMPLE_START_TIME,
            end_time=SAMPLE_END_TIME,
        )

    result = proxy.get_children_batch([SAMPLE_CHILD_RUN_ID_A, SAMPLE_CHILD_RUN_ID_B])

    assert SAMPLE_CHILD_RUN_ID_A in result
    assert len(result[SAMPLE_CHILD_RUN_ID_A]) == 2
    gc_names = {gc["name"] for gc in result[SAMPLE_CHILD_RUN_ID_A]}
    assert gc_names == {"grandchild-a1", "grandchild-a2"}
    # SAMPLE_CHILD_RUN_ID_B has no children, so it should not appear in the result
    assert SAMPLE_CHILD_RUN_ID_B not in result


def test_get_children_batch_empty_run_ids_returns_empty(proxy):
    """get_children_batch with an empty list returns an empty dict without error."""
    result = proxy.get_children_batch([])
    assert result == {}


# ─── Grandchild Rendering Endpoint Tests ─────────────────────────────────────


def _record_three_level_trace(proxy_instance, child_end: str = SAMPLE_END_TIME) -> None:
    """Write a root → child → grandchild hierarchy to the given proxy."""
    proxy_instance.record_run(
        run_id=SAMPLE_RUN_ID,
        parent_run_id=None,
        name=SAMPLE_RUN_NAME,
        inputs=None,
        outputs=None,
        metadata=None,
        error=None,
        start_time=SAMPLE_START_TIME,
        end_time=SAMPLE_END_TIME,
    )
    proxy_instance.record_run(
        run_id=SAMPLE_CHILD_RUN_ID_A,
        parent_run_id=SAMPLE_RUN_ID,
        name="execute_plan",
        inputs=None,
        outputs=None,
        metadata=None,
        error=None,
        start_time=SAMPLE_START_TIME,
        end_time=child_end,
    )
    proxy_instance.record_run(
        run_id=SAMPLE_GRANDCHILD_RUN_ID,
        parent_run_id=SAMPLE_CHILD_RUN_ID_A,
        name=SAMPLE_GRANDCHILD_NAME,
        inputs=None,
        outputs=None,
        metadata=None,
        error=None,
        start_time=SAMPLE_START_TIME,
        end_time=SAMPLE_END_TIME,
    )


def test_proxy_detail_grandchild_name_in_svg(enabled_client):
    """GET /proxy/{run_id} renders grandchild tool call as an aria-label in the SVG."""
    proxy_instance = get_proxy()
    assert proxy_instance is not None
    _record_three_level_trace(proxy_instance)

    response = enabled_client.get(f"/proxy/{SAMPLE_RUN_ID}")
    assert response.status_code == 200
    # The grandchild bar is rendered with aria-label="{{ gc.name }}: ..."
    assert f'aria-label="{SAMPLE_GRANDCHILD_NAME}:' in response.text


def test_proxy_detail_grandchild_name_in_expandable_section(enabled_client):
    """GET /proxy/{run_id} renders grandchild name in the expandable details section."""
    proxy_instance = get_proxy()
    assert proxy_instance is not None
    _record_three_level_trace(proxy_instance)

    response = enabled_client.get(f"/proxy/{SAMPLE_RUN_ID}")
    assert response.status_code == 200
    # Expandable section has "(1 tool call)" summary and the grandchild name in a span
    assert "1 tool call" in response.text
    assert SAMPLE_GRANDCHILD_NAME in response.text


def test_proxy_detail_grandchild_extends_svg_height(enabled_client):
    """SVG height increases when grandchild rows are present.

    With 1 child and 1 grandchild the total_rows = 2.
    Without grandchildren total_rows = 1.
    SVG_H = PAD_TOP + total_rows * ROW_H + AXIS_H = 10 + rows*30 + 36.
    """
    PAD_TOP = 10
    ROW_H = 30
    AXIS_H = 36

    proxy_instance = get_proxy()
    assert proxy_instance is not None

    # First: root + child only (no grandchild)
    proxy_instance.record_run(
        run_id="height-root",
        parent_run_id=None,
        name="height-test",
        inputs=None,
        outputs=None,
        metadata=None,
        error=None,
        start_time=SAMPLE_START_TIME,
        end_time=SAMPLE_END_TIME,
    )
    proxy_instance.record_run(
        run_id="height-child",
        parent_run_id="height-root",
        name="child-only",
        inputs=None,
        outputs=None,
        metadata=None,
        error=None,
        start_time=SAMPLE_START_TIME,
        end_time=SAMPLE_END_TIME,
    )

    resp_no_gc = enabled_client.get("/proxy/height-root")
    assert resp_no_gc.status_code == 200
    expected_height_1_row = PAD_TOP + 1 * ROW_H + AXIS_H
    assert f'height="{expected_height_1_row}"' in resp_no_gc.text

    # Add a grandchild under height-child
    proxy_instance.record_run(
        run_id="height-grandchild",
        parent_run_id="height-child",
        name="Bash",
        inputs=None,
        outputs=None,
        metadata=None,
        error=None,
        start_time=SAMPLE_START_TIME,
        end_time=SAMPLE_END_TIME,
    )

    resp_with_gc = enabled_client.get("/proxy/height-root")
    assert resp_with_gc.status_code == 200
    expected_height_2_rows = PAD_TOP + 2 * ROW_H + AXIS_H
    assert f'height="{expected_height_2_rows}"' in resp_with_gc.text


def test_proxy_detail_grandchild_later_end_extends_span(enabled_client):
    """span_s is computed from grandchild end times, not just children.

    When a grandchild ends later than its parent child, the SVG still renders
    correctly (no division-by-zero or template error) and the grandchild
    name appears in the output.
    """
    proxy_instance = get_proxy()
    assert proxy_instance is not None
    # Grandchild ends at SAMPLE_GRANDCHILD_END_TIME (10s after root start),
    # parent child ends at SAMPLE_END_TIME (5s). span_s must use the grandchild.
    _record_three_level_trace(proxy_instance, child_end=SAMPLE_END_TIME)

    response = enabled_client.get(f"/proxy/{SAMPLE_RUN_ID}")
    assert response.status_code == 200
    assert "<svg" in response.text
    assert SAMPLE_GRANDCHILD_NAME in response.text


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


# ─── Sub-Second Precision Tests ───────────────────────────────────────────────

SUB_SECOND_ROOT_TIME = "2026-03-27T05:11:52.000000"
SUB_SECOND_CHILD_A_START = "2026-03-27T05:11:53.016586"
SUB_SECOND_CHILD_A_END = "2026-03-27T05:11:53.017000"
SUB_SECOND_CHILD_B_START = "2026-03-27T05:11:53.018000"
SUB_SECOND_CHILD_B_END = "2026-03-27T05:11:53.020070"


def test_compute_elapsed_preserves_microsecond_precision():
    """_compute_elapsed produces sub-second float offsets from microsecond timestamps.

    Children within the same clock second must have distinct elapsed_start_s
    values so the Gantt chart renders them at different x positions.
    """
    root_start = _parse_iso(SUB_SECOND_ROOT_TIME)
    assert root_start is not None

    child_a = {
        "start_time": SUB_SECOND_CHILD_A_START,
        "end_time": SUB_SECOND_CHILD_A_END,
    }
    child_b = {
        "start_time": SUB_SECOND_CHILD_B_START,
        "end_time": SUB_SECOND_CHILD_B_END,
    }

    result_a = _compute_elapsed(child_a, root_start)
    result_b = _compute_elapsed(child_b, root_start)

    # Both offsets must be positive floats with sub-second resolution
    assert result_a["elapsed_start_s"] > 0.0
    assert result_b["elapsed_start_s"] > result_a["elapsed_start_s"]

    # The difference must reflect millisecond-level separation (~1.4 ms)
    diff = result_b["elapsed_start_s"] - result_a["elapsed_start_s"]
    assert 0.001 < diff < 0.005


def test_proxy_detail_sub_second_children_render_without_error(enabled_client):
    """GET /proxy/{run_id} renders cleanly when all children complete within 1 second.

    Reproduces the bug scenario: 10 children with start_times varying by only 4 ms.
    The SVG must render (no template error / division-by-zero) and the chart area
    must be present.
    """
    proxy_instance = get_proxy()
    assert proxy_instance is not None

    sub_root_id = "sub-second-root"
    proxy_instance.record_run(
        run_id=sub_root_id,
        parent_run_id=None,
        name="fast-pipeline",
        inputs=None,
        outputs=None,
        metadata=None,
        error=None,
        start_time=SUB_SECOND_ROOT_TIME,
        end_time=SUB_SECOND_CHILD_B_END,
    )
    # Two children separated by ~1.4 ms (mirrors the 4 ms real-world case)
    proxy_instance.record_run(
        run_id="sub-child-a",
        parent_run_id=sub_root_id,
        name="step-a",
        inputs=None,
        outputs=None,
        metadata=None,
        error=None,
        start_time=SUB_SECOND_CHILD_A_START,
        end_time=SUB_SECOND_CHILD_A_END,
    )
    proxy_instance.record_run(
        run_id="sub-child-b",
        parent_run_id=sub_root_id,
        name="step-b",
        inputs=None,
        outputs=None,
        metadata=None,
        error=None,
        start_time=SUB_SECOND_CHILD_B_START,
        end_time=SUB_SECOND_CHILD_B_END,
    )

    response = enabled_client.get(f"/proxy/{sub_root_id}")
    assert response.status_code == 200
    assert "<svg" in response.text
    # Axis ticks must use ms labels for sub-second spans
    assert "ms" in response.text
