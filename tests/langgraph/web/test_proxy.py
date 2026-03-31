# tests/langgraph/web/test_proxy.py
# Unit tests for TracingProxy (SQLite persistence).
# Design: docs/plans/2026-03-25-14-langsmith-tracing-proxy-design.md
# Design: docs/plans/2026-03-26-16-tool-calls-missing-from-traces-design.md

"""Unit tests for langgraph_pipeline.web.proxy (TracingProxy data layer)."""

import json
import sqlite3
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import langgraph_pipeline.web.proxy as proxy_module
from langgraph_pipeline.web.proxy import ChildTimeSpan, DailyTotal, Session, TracingProxy, get_proxy, init_proxy
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


def test_upsert_with_null_end_time_preserves_existing_end_time(proxy):
    """Re-posting a completed root run with end_time=None does not clear the stored end_time.

    This covers the create_root_run() recovery scenario: if a worker is restarted
    and the root run is re-posted without an end_time, the completed end_time from
    finalize_root_run() must not be wiped out.
    """
    # Finalize sets end_time
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
    # Re-post with no end_time (create_root_run recovery path)
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

    row = proxy.get_run(SAMPLE_RUN_ID)
    assert row is not None
    # COALESCE must preserve the existing end_time when excluded.end_time is NULL
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


# ─── Two-Pass Inclusive Cost Tests ────────────────────────────────────────────

COST_ROOT_RUN_ID = "cost-root-run-1a2b"
COST_CHILD_RUN_ID_A = "cost-child-run-3c4d"
COST_CHILD_RUN_ID_B = "cost-child-run-5e6f"
COST_ROOT_RUN_ID_2 = "cost-root-run-7g8h"

COST_ROOT_COST = 0.4732
COST_CHILD_A_COST = 0.1891
COST_CHILD_B_COST = 0.2314
COST_ROOT_2_COST = 0.3156


def _record_cost_run(proxy, run_id, parent_run_id, cost_usd, item_slug="test-feature"):
    """Helper: record a trace run with cost metadata."""
    proxy.record_run(
        run_id=run_id,
        parent_run_id=parent_run_id,
        name=f"run-{run_id[-4:]}",
        inputs=None,
        outputs=None,
        metadata={
            "total_cost_usd": cost_usd,
            "item_slug": item_slug,
            "item_type": "feature",
            "input_tokens": 1000,
            "output_tokens": 500,
            "duration_ms": 1200,
        },
        error=None,
        start_time=SAMPLE_START_TIME,
        end_time=SAMPLE_END_TIME,
    )


def test_compute_inclusive_costs_empty(proxy):
    """_compute_inclusive_costs returns an empty dict for an empty input list."""
    result = proxy._compute_inclusive_costs([])
    assert result == {}


def test_compute_inclusive_costs_leaf_only(proxy):
    """_compute_inclusive_costs returns own cost when run has no descendants."""
    _record_cost_run(proxy, COST_ROOT_RUN_ID, None, COST_ROOT_COST)

    result = proxy._compute_inclusive_costs([COST_ROOT_RUN_ID])

    assert COST_ROOT_RUN_ID in result
    assert abs(result[COST_ROOT_RUN_ID] - COST_ROOT_COST) < 1e-9


def test_compute_inclusive_costs_with_children(proxy):
    """_compute_inclusive_costs sums root + all descendant costs."""
    _record_cost_run(proxy, COST_ROOT_RUN_ID, None, COST_ROOT_COST)
    _record_cost_run(proxy, COST_CHILD_RUN_ID_A, COST_ROOT_RUN_ID, COST_CHILD_A_COST)
    _record_cost_run(proxy, COST_CHILD_RUN_ID_B, COST_ROOT_RUN_ID, COST_CHILD_B_COST)

    result = proxy._compute_inclusive_costs([COST_ROOT_RUN_ID])

    expected = COST_ROOT_COST + COST_CHILD_A_COST + COST_CHILD_B_COST
    assert abs(result[COST_ROOT_RUN_ID] - expected) < 1e-9


def test_compute_inclusive_costs_multi_anchor(proxy):
    """_compute_inclusive_costs handles multiple independent roots in one call."""
    _record_cost_run(proxy, COST_ROOT_RUN_ID, None, COST_ROOT_COST)
    _record_cost_run(proxy, COST_CHILD_RUN_ID_A, COST_ROOT_RUN_ID, COST_CHILD_A_COST)
    _record_cost_run(proxy, COST_ROOT_RUN_ID_2, None, COST_ROOT_2_COST)

    result = proxy._compute_inclusive_costs([COST_ROOT_RUN_ID, COST_ROOT_RUN_ID_2])

    expected_root1 = COST_ROOT_COST + COST_CHILD_A_COST
    assert abs(result[COST_ROOT_RUN_ID] - expected_root1) < 1e-9
    assert abs(result[COST_ROOT_RUN_ID_2] - COST_ROOT_2_COST) < 1e-9


def test_list_cost_runs_returns_inclusive_cost(proxy):
    """list_cost_runs enriches rows with inclusive cost via two-pass strategy."""
    _record_cost_run(proxy, COST_ROOT_RUN_ID, None, COST_ROOT_COST)
    _record_cost_run(proxy, COST_CHILD_RUN_ID_A, COST_ROOT_RUN_ID, COST_CHILD_A_COST)
    _record_cost_run(proxy, COST_CHILD_RUN_ID_B, COST_ROOT_RUN_ID, COST_CHILD_B_COST)

    runs, total = proxy.list_cost_runs(page=1, sort="exclusive_desc")

    # Only the root row should appear (it has item_slug metadata)
    root_row = next((r for r in runs if r.run_id == COST_ROOT_RUN_ID), None)
    assert root_row is not None
    assert abs(root_row.exclusive_cost_usd - COST_ROOT_COST) < 1e-9

    expected_inclusive = COST_ROOT_COST + COST_CHILD_A_COST + COST_CHILD_B_COST
    assert abs(root_row.inclusive_cost_usd - expected_inclusive) < 1e-9


def test_list_cost_runs_inclusive_desc_sort(proxy):
    """list_cost_runs with inclusive_desc sorts page rows by inclusive cost."""
    # root1 has children so its inclusive cost exceeds root2's exclusive cost
    _record_cost_run(proxy, COST_ROOT_RUN_ID, None, COST_ROOT_COST, item_slug="slug-a")
    _record_cost_run(proxy, COST_CHILD_RUN_ID_A, COST_ROOT_RUN_ID, COST_CHILD_A_COST, item_slug="slug-a")
    _record_cost_run(proxy, COST_ROOT_RUN_ID_2, None, COST_ROOT_2_COST, item_slug="slug-b")

    runs, _ = proxy.list_cost_runs(page=1, sort="inclusive_desc")

    assert len(runs) >= 2
    # Rows must be ordered by inclusive_cost_usd descending
    for i in range(len(runs) - 1):
        assert runs[i].inclusive_cost_usd >= runs[i + 1].inclusive_cost_usd


def test_list_cost_runs_empty_db(proxy):
    """list_cost_runs returns empty list and zero total on an empty database."""
    runs, total = proxy.list_cost_runs(page=1)
    assert runs == []
    assert total == 0


def test_list_cost_runs_pagination(proxy):
    """list_cost_runs respects page/page_size and returns correct total_count."""
    for i in range(5):
        run_id = f"cost-page-run-{i:04d}"
        _record_cost_run(proxy, run_id, None, round(0.1 + i * 0.07, 4), item_slug=f"slug-{i}")

    runs_p1, total = proxy.list_cost_runs(page=1, page_size=3, sort="exclusive_desc")
    runs_p2, _ = proxy.list_cost_runs(page=2, page_size=3, sort="exclusive_desc")

    assert total == 5
    assert len(runs_p1) == 3
    assert len(runs_p2) == 2
    # No overlap between pages
    ids_p1 = {r.run_id for r in runs_p1}
    ids_p2 = {r.run_id for r in runs_p2}
    assert ids_p1.isdisjoint(ids_p2)


# ─── Sessions Tests ───────────────────────────────────────────────────────────


def test_create_session_returns_id(proxy):
    """create_session() inserts a row and returns a positive integer id."""
    session_id = proxy.create_session(label="Morning run")
    assert isinstance(session_id, int)
    assert session_id > 0


def test_create_session_closes_orphans(proxy):
    """create_session() closes any open sessions before creating a new one."""
    first_id = proxy.create_session(label="First")
    # First session is open (end_time IS NULL)
    sessions = proxy.list_sessions()
    assert len(sessions) == 1
    assert sessions[0].end_time is None

    # Creating a second session should close the first
    second_id = proxy.create_session(label="Second")
    sessions = proxy.list_sessions()
    assert len(sessions) == 2

    # The first session (older, so last in DESC order) must now be closed
    first_session = next(s for s in sessions if s.id == first_id)
    assert first_session.end_time is not None

    # The second session is still open
    second_session = next(s for s in sessions if s.id == second_id)
    assert second_session.end_time is None


def test_close_session_sets_end_time_and_totals(proxy):
    """close_session() updates end_time, total_cost_usd, and items_processed."""
    session_id = proxy.create_session()
    proxy.close_session(session_id, total_cost_usd=1.2345, items_processed=7)

    sessions = proxy.list_sessions()
    assert len(sessions) == 1
    s = sessions[0]
    assert s.end_time is not None
    assert abs(s.total_cost_usd - 1.2345) < 1e-6
    assert s.items_processed == 7


def test_list_sessions_ordered_newest_first(proxy):
    """list_sessions() returns sessions newest-first."""
    id1 = proxy.create_session(label="alpha")
    id2 = proxy.create_session(label="beta")  # closes alpha, creates beta

    sessions = proxy.list_sessions()
    assert sessions[0].id == id2
    assert sessions[1].id == id1


def test_list_sessions_empty(proxy):
    """list_sessions() returns an empty list when no sessions exist."""
    assert proxy.list_sessions() == []


def test_list_daily_totals_aggregates_by_day(proxy):
    """list_daily_totals() sums cost_usd and counts rows per calendar day."""
    # Insert two completions on 2026-03-20 and one on 2026-03-21
    import sqlite3

    with sqlite3.connect(str(proxy._db_path)) as conn:
        conn.execute(
            "INSERT INTO completions (slug, item_type, outcome, cost_usd, duration_s, finished_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            ["slug-a", "feature", "success", 0.50, 10.0, "2026-03-20T08:00:00"],
        )
        conn.execute(
            "INSERT INTO completions (slug, item_type, outcome, cost_usd, duration_s, finished_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            ["slug-b", "feature", "success", 0.30, 5.0, "2026-03-20T12:00:00"],
        )
        conn.execute(
            "INSERT INTO completions (slug, item_type, outcome, cost_usd, duration_s, finished_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            ["slug-c", "defect", "success", 0.20, 3.0, "2026-03-21T09:00:00"],
        )

    totals = proxy.list_daily_totals()
    assert len(totals) == 2

    # Newest day first
    assert totals[0].date_str == "2026-03-21"
    assert abs(totals[0].cost_usd - 0.20) < 1e-6
    assert totals[0].items_processed == 1

    assert totals[1].date_str == "2026-03-20"
    assert abs(totals[1].cost_usd - 0.80) < 1e-6
    assert totals[1].items_processed == 2


def test_list_daily_totals_empty(proxy):
    """list_daily_totals() returns an empty list when completions table is empty."""
    assert proxy.list_daily_totals() == []


def test_session_dataclass_fields(proxy):
    """Session returned by list_sessions() has all expected fields."""
    session_id = proxy.create_session(label="test-label")
    sessions = proxy.list_sessions()
    assert len(sessions) == 1
    s = sessions[0]
    assert isinstance(s, Session)
    assert s.id == session_id
    assert s.label == "test-label"
    assert s.start_time is not None
    assert s.end_time is None
    assert s.total_cost_usd == 0.0
    assert s.items_processed == 0
    assert s.notes is None


# ─── get_child_time_spans_batch Tests ────────────────────────────────────────


CHILD_SPAN_PARENT_A = "parent-span-a"
CHILD_SPAN_PARENT_B = "parent-span-b"
CHILD_SPAN_CHILD_A1 = "child-span-a1"
CHILD_SPAN_CHILD_A2 = "child-span-a2"
CHILD_SPAN_CHILD_B1 = "child-span-b1"


def test_get_child_time_spans_batch_empty_input(proxy):
    """get_child_time_spans_batch([]) returns an empty dict without querying the DB."""
    result = proxy.get_child_time_spans_batch([])
    assert result == {}


def test_get_child_time_spans_batch_no_children(proxy):
    """Parent run_id with no children is absent from the result dict."""
    proxy.record_run(
        run_id=CHILD_SPAN_PARENT_A,
        parent_run_id=None,
        name="lone-parent",
        inputs=None,
        outputs=None,
        metadata=None,
        error=None,
        start_time="2026-03-28T09:00:00",
        end_time="2026-03-28T09:01:00",
    )
    result = proxy.get_child_time_spans_batch([CHILD_SPAN_PARENT_A])
    assert CHILD_SPAN_PARENT_A not in result


def test_get_child_time_spans_batch_single_parent(proxy):
    """Returns correct earliest start and latest end across two children of one parent."""
    proxy.record_run(
        run_id=CHILD_SPAN_PARENT_A,
        parent_run_id=None,
        name="root-run",
        inputs=None,
        outputs=None,
        metadata=None,
        error=None,
        start_time="2026-03-28T09:00:00",
        end_time="2026-03-28T09:00:01",
    )
    # First child: starts earlier, ends earlier
    proxy.record_run(
        run_id=CHILD_SPAN_CHILD_A1,
        parent_run_id=CHILD_SPAN_PARENT_A,
        name="phase-1",
        inputs=None,
        outputs=None,
        metadata=None,
        error=None,
        start_time="2026-03-28T09:00:10",
        end_time="2026-03-28T09:05:00",
    )
    # Second child: starts later, ends later
    proxy.record_run(
        run_id=CHILD_SPAN_CHILD_A2,
        parent_run_id=CHILD_SPAN_PARENT_A,
        name="phase-2",
        inputs=None,
        outputs=None,
        metadata=None,
        error=None,
        start_time="2026-03-28T09:05:30",
        end_time="2026-03-28T09:12:00",
    )

    result = proxy.get_child_time_spans_batch([CHILD_SPAN_PARENT_A])

    assert CHILD_SPAN_PARENT_A in result
    span = result[CHILD_SPAN_PARENT_A]
    assert isinstance(span, ChildTimeSpan)
    assert span.earliest_start == "2026-03-28T09:00:10"
    assert span.latest_end == "2026-03-28T09:12:00"


def test_get_child_time_spans_batch_multiple_parents(proxy):
    """Returns correct spans for two parents in a single batch query."""
    # Parent A with two children
    proxy.record_run(
        run_id=CHILD_SPAN_PARENT_A,
        parent_run_id=None,
        name="root-a",
        inputs=None, outputs=None, metadata=None, error=None,
        start_time="2026-03-28T08:00:00",
        end_time="2026-03-28T08:00:01",
    )
    proxy.record_run(
        run_id=CHILD_SPAN_CHILD_A1,
        parent_run_id=CHILD_SPAN_PARENT_A,
        name="child-a1",
        inputs=None, outputs=None, metadata=None, error=None,
        start_time="2026-03-28T08:01:00",
        end_time="2026-03-28T08:10:00",
    )
    proxy.record_run(
        run_id=CHILD_SPAN_CHILD_A2,
        parent_run_id=CHILD_SPAN_PARENT_A,
        name="child-a2",
        inputs=None, outputs=None, metadata=None, error=None,
        start_time="2026-03-28T08:11:00",
        end_time="2026-03-28T08:20:00",
    )
    # Parent B with one child
    proxy.record_run(
        run_id=CHILD_SPAN_PARENT_B,
        parent_run_id=None,
        name="root-b",
        inputs=None, outputs=None, metadata=None, error=None,
        start_time="2026-03-28T10:00:00",
        end_time="2026-03-28T10:00:01",
    )
    proxy.record_run(
        run_id=CHILD_SPAN_CHILD_B1,
        parent_run_id=CHILD_SPAN_PARENT_B,
        name="child-b1",
        inputs=None, outputs=None, metadata=None, error=None,
        start_time="2026-03-28T10:03:00",
        end_time="2026-03-28T10:07:30",
    )

    result = proxy.get_child_time_spans_batch([CHILD_SPAN_PARENT_A, CHILD_SPAN_PARENT_B])

    assert len(result) == 2

    span_a = result[CHILD_SPAN_PARENT_A]
    assert span_a.earliest_start == "2026-03-28T08:01:00"
    assert span_a.latest_end == "2026-03-28T08:20:00"

    span_b = result[CHILD_SPAN_PARENT_B]
    assert span_b.earliest_start == "2026-03-28T10:03:00"
    assert span_b.latest_end == "2026-03-28T10:07:30"


def test_get_child_time_spans_batch_null_end_time(proxy):
    """A child with NULL end_time does not break aggregation; latest_end may be None."""
    proxy.record_run(
        run_id=CHILD_SPAN_PARENT_A,
        parent_run_id=None,
        name="root-run",
        inputs=None, outputs=None, metadata=None, error=None,
        start_time="2026-03-28T09:00:00",
        end_time=None,
    )
    proxy.record_run(
        run_id=CHILD_SPAN_CHILD_A1,
        parent_run_id=CHILD_SPAN_PARENT_A,
        name="still-running",
        inputs=None, outputs=None, metadata=None, error=None,
        start_time="2026-03-28T09:01:00",
        end_time=None,
    )

    result = proxy.get_child_time_spans_batch([CHILD_SPAN_PARENT_A])

    assert CHILD_SPAN_PARENT_A in result
    span = result[CHILD_SPAN_PARENT_A]
    assert span.earliest_start == "2026-03-28T09:01:00"
    assert span.latest_end is None


# ─── get_child_costs_batch Tests ─────────────────────────────────────────────

COST_PARENT_A = "cost-parent-a"
COST_PARENT_B = "cost-parent-b"
COST_CHILD_A1 = "cost-child-a1"
COST_CHILD_A2 = "cost-child-a2"
COST_GRANDCHILD_A1 = "cost-grandchild-a1"
COST_CHILD_B1 = "cost-child-b1"


def test_get_child_costs_batch_empty_input(proxy):
    """get_child_costs_batch([]) returns an empty dict without querying the DB."""
    result = proxy.get_child_costs_batch([])
    assert result == {}


def test_get_child_costs_batch_no_cost_data(proxy):
    """Parent with children that have no total_cost_usd is absent from the result."""
    proxy.record_run(
        run_id=COST_PARENT_A,
        parent_run_id=None,
        name="root-run",
        inputs=None, outputs=None, metadata=None, error=None,
        start_time="2026-03-28T10:00:00",
        end_time="2026-03-28T10:00:01",
    )
    proxy.record_run(
        run_id=COST_CHILD_A1,
        parent_run_id=COST_PARENT_A,
        name="child-no-cost",
        inputs=None, outputs=None,
        metadata={"other_field": "value"},
        error=None,
        start_time="2026-03-28T10:01:00",
        end_time="2026-03-28T10:02:00",
    )
    result = proxy.get_child_costs_batch([COST_PARENT_A])
    assert COST_PARENT_A not in result


def test_get_child_costs_batch_direct_children(proxy):
    """Sums total_cost_usd from direct children of the parent."""
    proxy.record_run(
        run_id=COST_PARENT_A,
        parent_run_id=None,
        name="root-run",
        inputs=None, outputs=None, metadata=None, error=None,
        start_time="2026-03-28T10:00:00",
        end_time="2026-03-28T10:00:01",
    )
    proxy.record_run(
        run_id=COST_CHILD_A1,
        parent_run_id=COST_PARENT_A,
        name="execute-task",
        inputs=None, outputs=None,
        metadata={"total_cost_usd": 1.25},
        error=None,
        start_time="2026-03-28T10:01:00",
        end_time="2026-03-28T10:03:00",
    )
    proxy.record_run(
        run_id=COST_CHILD_A2,
        parent_run_id=COST_PARENT_A,
        name="validate-task",
        inputs=None, outputs=None,
        metadata={"total_cost_usd": 0.75},
        error=None,
        start_time="2026-03-28T10:03:30",
        end_time="2026-03-28T10:05:00",
    )
    result = proxy.get_child_costs_batch([COST_PARENT_A])
    assert COST_PARENT_A in result
    assert abs(result[COST_PARENT_A] - 2.0) < 1e-9


def test_get_child_costs_batch_includes_grandchildren(proxy):
    """Recursively sums cost from grandchildren as well as direct children."""
    proxy.record_run(
        run_id=COST_PARENT_A,
        parent_run_id=None,
        name="root-run",
        inputs=None, outputs=None, metadata=None, error=None,
        start_time="2026-03-28T10:00:00",
        end_time="2026-03-28T10:00:01",
    )
    proxy.record_run(
        run_id=COST_CHILD_A1,
        parent_run_id=COST_PARENT_A,
        name="child-with-cost",
        inputs=None, outputs=None,
        metadata={"total_cost_usd": 0.50},
        error=None,
        start_time="2026-03-28T10:01:00",
        end_time="2026-03-28T10:02:00",
    )
    proxy.record_run(
        run_id=COST_GRANDCHILD_A1,
        parent_run_id=COST_CHILD_A1,
        name="grandchild-with-cost",
        inputs=None, outputs=None,
        metadata={"total_cost_usd": 0.30},
        error=None,
        start_time="2026-03-28T10:01:10",
        end_time="2026-03-28T10:01:50",
    )
    result = proxy.get_child_costs_batch([COST_PARENT_A])
    assert COST_PARENT_A in result
    assert abs(result[COST_PARENT_A] - 0.80) < 1e-9


def test_get_child_costs_batch_multiple_parents(proxy):
    """Returns correct costs for two parents in a single batch query."""
    proxy.record_run(
        run_id=COST_PARENT_A,
        parent_run_id=None,
        name="root-a",
        inputs=None, outputs=None, metadata=None, error=None,
        start_time="2026-03-28T08:00:00",
        end_time="2026-03-28T08:00:01",
    )
    proxy.record_run(
        run_id=COST_CHILD_A1,
        parent_run_id=COST_PARENT_A,
        name="child-a1",
        inputs=None, outputs=None,
        metadata={"total_cost_usd": 3.10},
        error=None,
        start_time="2026-03-28T08:01:00",
        end_time="2026-03-28T08:10:00",
    )
    proxy.record_run(
        run_id=COST_PARENT_B,
        parent_run_id=None,
        name="root-b",
        inputs=None, outputs=None, metadata=None, error=None,
        start_time="2026-03-28T09:00:00",
        end_time="2026-03-28T09:00:01",
    )
    proxy.record_run(
        run_id=COST_CHILD_B1,
        parent_run_id=COST_PARENT_B,
        name="child-b1",
        inputs=None, outputs=None,
        metadata={"total_cost_usd": 1.40},
        error=None,
        start_time="2026-03-28T09:01:00",
        end_time="2026-03-28T09:05:00",
    )
    result = proxy.get_child_costs_batch([COST_PARENT_A, COST_PARENT_B])
    assert len(result) == 2
    assert abs(result[COST_PARENT_A] - 3.10) < 1e-9
    assert abs(result[COST_PARENT_B] - 1.40) < 1e-9


# ─── get_child_models_batch Tests ────────────────────────────────────────────

MODEL_PARENT_A = "model-parent-a"
MODEL_PARENT_B = "model-parent-b"
MODEL_CHILD_A1 = "model-child-a1"
MODEL_CHILD_A2 = "model-child-a2"
MODEL_CHILD_A3 = "model-child-a3"
MODEL_CHILD_B1 = "model-child-b1"


def test_get_child_models_batch_empty_input(proxy):
    """get_child_models_batch([]) returns an empty dict without querying the DB."""
    result = proxy.get_child_models_batch([])
    assert result == {}


def test_get_child_models_batch_no_model_children(proxy):
    """Parent whose children have no model value is absent from the result."""
    proxy.record_run(
        run_id=MODEL_PARENT_A,
        parent_run_id=None,
        name="root-run",
        inputs=None, outputs=None, metadata=None, error=None,
        start_time="2026-03-28T10:00:00",
        end_time="2026-03-28T10:00:01",
    )
    proxy.record_run(
        run_id=MODEL_CHILD_A1,
        parent_run_id=MODEL_PARENT_A,
        name="child-no-model",
        inputs=None, outputs=None, metadata={}, error=None,
        start_time="2026-03-28T10:01:00",
        end_time="2026-03-28T10:02:00",
    )
    result = proxy.get_child_models_batch([MODEL_PARENT_A])
    assert MODEL_PARENT_A not in result


def test_get_child_models_batch_most_common_model(proxy):
    """Returns the model that appears most frequently among direct children."""
    proxy.record_run(
        run_id=MODEL_PARENT_A,
        parent_run_id=None,
        name="root-run",
        inputs=None, outputs=None, metadata=None, error=None,
        start_time="2026-03-28T10:00:00",
        end_time="2026-03-28T10:00:01",
    )
    # Two children with "claude-sonnet-4-6", one with "claude-haiku-4-5"
    proxy.record_run(
        run_id=MODEL_CHILD_A1,
        parent_run_id=MODEL_PARENT_A,
        name="child-1",
        inputs=None, outputs=None,
        metadata={"model": "claude-sonnet-4-6"},
        error=None,
        start_time="2026-03-28T10:01:00",
        end_time="2026-03-28T10:02:00",
    )
    proxy.record_run(
        run_id=MODEL_CHILD_A2,
        parent_run_id=MODEL_PARENT_A,
        name="child-2",
        inputs=None, outputs=None,
        metadata={"model": "claude-haiku-4-5"},
        error=None,
        start_time="2026-03-28T10:02:00",
        end_time="2026-03-28T10:03:00",
    )
    proxy.record_run(
        run_id=MODEL_CHILD_A3,
        parent_run_id=MODEL_PARENT_A,
        name="child-3",
        inputs=None, outputs=None,
        metadata={"model": "claude-sonnet-4-6"},
        error=None,
        start_time="2026-03-28T10:03:00",
        end_time="2026-03-28T10:04:00",
    )
    result = proxy.get_child_models_batch([MODEL_PARENT_A])
    assert MODEL_PARENT_A in result
    assert result[MODEL_PARENT_A] == "claude-sonnet-4-6"


def test_get_child_models_batch_tie_broken_alphabetically(proxy):
    """When two models appear equally often, the alphabetically first is returned."""
    proxy.record_run(
        run_id=MODEL_PARENT_A,
        parent_run_id=None,
        name="root-run",
        inputs=None, outputs=None, metadata=None, error=None,
        start_time="2026-03-28T10:00:00",
        end_time="2026-03-28T10:00:01",
    )
    proxy.record_run(
        run_id=MODEL_CHILD_A1,
        parent_run_id=MODEL_PARENT_A,
        name="child-1",
        inputs=None, outputs=None,
        metadata={"model": "claude-sonnet-4-6"},
        error=None,
        start_time="2026-03-28T10:01:00",
        end_time="2026-03-28T10:02:00",
    )
    proxy.record_run(
        run_id=MODEL_CHILD_A2,
        parent_run_id=MODEL_PARENT_A,
        name="child-2",
        inputs=None, outputs=None,
        metadata={"model": "claude-haiku-4-5"},
        error=None,
        start_time="2026-03-28T10:02:00",
        end_time="2026-03-28T10:03:00",
    )
    result = proxy.get_child_models_batch([MODEL_PARENT_A])
    assert MODEL_PARENT_A in result
    # "claude-haiku-4-5" comes before "claude-sonnet-4-6" alphabetically
    assert result[MODEL_PARENT_A] == "claude-haiku-4-5"


def test_get_child_models_batch_multiple_parents(proxy):
    """Returns correct model for two parents in a single batch query."""
    proxy.record_run(
        run_id=MODEL_PARENT_A,
        parent_run_id=None,
        name="root-a",
        inputs=None, outputs=None, metadata=None, error=None,
        start_time="2026-03-28T08:00:00",
        end_time="2026-03-28T08:00:01",
    )
    proxy.record_run(
        run_id=MODEL_CHILD_A1,
        parent_run_id=MODEL_PARENT_A,
        name="child-a",
        inputs=None, outputs=None,
        metadata={"model": "claude-opus-4-6"},
        error=None,
        start_time="2026-03-28T08:01:00",
        end_time="2026-03-28T08:10:00",
    )
    proxy.record_run(
        run_id=MODEL_PARENT_B,
        parent_run_id=None,
        name="root-b",
        inputs=None, outputs=None, metadata=None, error=None,
        start_time="2026-03-28T09:00:00",
        end_time="2026-03-28T09:00:01",
    )
    proxy.record_run(
        run_id=MODEL_CHILD_B1,
        parent_run_id=MODEL_PARENT_B,
        name="child-b",
        inputs=None, outputs=None,
        metadata={"model": "claude-haiku-4-5"},
        error=None,
        start_time="2026-03-28T09:01:00",
        end_time="2026-03-28T09:05:00",
    )
    result = proxy.get_child_models_batch([MODEL_PARENT_A, MODEL_PARENT_B])
    assert len(result) == 2
    assert result[MODEL_PARENT_A] == "claude-opus-4-6"
    assert result[MODEL_PARENT_B] == "claude-haiku-4-5"


# ─── get_child_slugs_batch Tests ─────────────────────────────────────────────


SLUG_PARENT_A = "slug-parent-a"
SLUG_PARENT_B = "slug-parent-b"
SLUG_CHILD_A1 = "slug-child-a1"
SLUG_CHILD_A2 = "slug-child-a2"
SLUG_CHILD_B1 = "slug-child-b1"


def test_get_child_slugs_batch_empty_input(proxy):
    """get_child_slugs_batch([]) returns an empty dict without querying the DB."""
    result = proxy.get_child_slugs_batch([])
    assert result == {}


def test_get_child_slugs_batch_no_slug_in_children(proxy):
    """Parent run_id with children that have no slug metadata is absent from result."""
    proxy.record_run(
        run_id=SLUG_PARENT_A,
        parent_run_id=None,
        name="LangGraph",
        inputs=None, outputs=None, metadata=None, error=None,
        start_time="2026-03-28T09:00:00",
        end_time="2026-03-28T09:00:01",
    )
    proxy.record_run(
        run_id=SLUG_CHILD_A1,
        parent_run_id=SLUG_PARENT_A,
        name="child-no-slug",
        inputs=None, outputs=None,
        metadata={"model": "claude-sonnet-4-6"},
        error=None,
        start_time="2026-03-28T09:00:10",
        end_time="2026-03-28T09:05:00",
    )
    result = proxy.get_child_slugs_batch([SLUG_PARENT_A])
    assert SLUG_PARENT_A not in result


def test_get_child_slugs_batch_item_slug_field(proxy):
    """Returns item_slug from child metadata when present."""
    proxy.record_run(
        run_id=SLUG_PARENT_A,
        parent_run_id=None,
        name="LangGraph",
        inputs=None, outputs=None, metadata=None, error=None,
        start_time="2026-03-28T09:00:00",
        end_time="2026-03-28T09:00:01",
    )
    proxy.record_run(
        run_id=SLUG_CHILD_A1,
        parent_run_id=SLUG_PARENT_A,
        name="executor",
        inputs=None, outputs=None,
        metadata={"item_slug": "42-fix-timeout-bug"},
        error=None,
        start_time="2026-03-28T09:00:10",
        end_time="2026-03-28T09:05:00",
    )
    result = proxy.get_child_slugs_batch([SLUG_PARENT_A])
    assert result[SLUG_PARENT_A] == "42-fix-timeout-bug"


def test_get_child_slugs_batch_slug_field_fallback(proxy):
    """Returns slug field from child metadata when item_slug is absent."""
    proxy.record_run(
        run_id=SLUG_PARENT_A,
        parent_run_id=None,
        name="LangGraph",
        inputs=None, outputs=None, metadata=None, error=None,
        start_time="2026-03-28T09:00:00",
        end_time="2026-03-28T09:00:01",
    )
    proxy.record_run(
        run_id=SLUG_CHILD_A1,
        parent_run_id=SLUG_PARENT_A,
        name="executor",
        inputs=None, outputs=None,
        metadata={"slug": "17-add-dark-mode"},
        error=None,
        start_time="2026-03-28T09:00:10",
        end_time="2026-03-28T09:05:00",
    )
    result = proxy.get_child_slugs_batch([SLUG_PARENT_A])
    assert result[SLUG_PARENT_A] == "17-add-dark-mode"


def test_get_child_slugs_batch_item_slug_beats_slug(proxy):
    """item_slug takes precedence over slug when both fields are present in metadata."""
    proxy.record_run(
        run_id=SLUG_PARENT_A,
        parent_run_id=None,
        name="LangGraph",
        inputs=None, outputs=None, metadata=None, error=None,
        start_time="2026-03-28T09:00:00",
        end_time="2026-03-28T09:00:01",
    )
    proxy.record_run(
        run_id=SLUG_CHILD_A1,
        parent_run_id=SLUG_PARENT_A,
        name="executor",
        inputs=None, outputs=None,
        metadata={"item_slug": "05-real-slug", "slug": "99-stale-slug"},
        error=None,
        start_time="2026-03-28T09:00:10",
        end_time="2026-03-28T09:05:00",
    )
    result = proxy.get_child_slugs_batch([SLUG_PARENT_A])
    assert result[SLUG_PARENT_A] == "05-real-slug"


def test_get_child_slugs_batch_multiple_parents(proxy):
    """Returns resolved slugs for two independent parent runs in one batch call."""
    proxy.record_run(
        run_id=SLUG_PARENT_A,
        parent_run_id=None,
        name="LangGraph",
        inputs=None, outputs=None, metadata=None, error=None,
        start_time="2026-03-28T09:00:00",
        end_time="2026-03-28T09:00:01",
    )
    proxy.record_run(
        run_id=SLUG_CHILD_A1,
        parent_run_id=SLUG_PARENT_A,
        name="executor",
        inputs=None, outputs=None,
        metadata={"item_slug": "11-feature-alpha"},
        error=None,
        start_time="2026-03-28T09:00:10",
        end_time="2026-03-28T09:05:00",
    )
    proxy.record_run(
        run_id=SLUG_PARENT_B,
        parent_run_id=None,
        name="LangGraph",
        inputs=None, outputs=None, metadata=None, error=None,
        start_time="2026-03-28T10:00:00",
        end_time="2026-03-28T10:00:01",
    )
    proxy.record_run(
        run_id=SLUG_CHILD_B1,
        parent_run_id=SLUG_PARENT_B,
        name="executor",
        inputs=None, outputs=None,
        metadata={"item_slug": "22-feature-beta"},
        error=None,
        start_time="2026-03-28T10:00:10",
        end_time="2026-03-28T10:08:00",
    )
    result = proxy.get_child_slugs_batch([SLUG_PARENT_A, SLUG_PARENT_B])
    assert len(result) == 2
    assert result[SLUG_PARENT_A] == "11-feature-alpha"
    assert result[SLUG_PARENT_B] == "22-feature-beta"


# ─── Completions Upsert Tests (AC1–AC29 subset for task 1.1) ─────────────────

# Constants for completion upsert tests
UPSERT_SLUG = "85-completions-upsert"
UPSERT_ITEM_TYPE = "feature"
UPSERT_RUN_ID_1 = "run-attempt-001"
UPSERT_RUN_ID_2 = "run-attempt-002"
UPSERT_NOTES_1 = '{"verdict": "warn", "findings": ["partial"]}'
UPSERT_NOTES_2 = '{"verdict": "success", "findings": []}'


def _read_completion_row(proxy: TracingProxy, slug: str) -> dict:
    """Read the single completion row for a given slug directly from SQLite."""
    with sqlite3.connect(str(proxy._db_path)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM completions WHERE slug = ?", [slug]
        ).fetchone()
    assert row is not None, f"No completion row found for slug={slug}"
    return dict(row)


def _count_completion_rows(proxy: TracingProxy, slug: str) -> int:
    """Return the number of completions rows for a given slug."""
    with sqlite3.connect(str(proxy._db_path)) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM completions WHERE slug = ?", [slug]
        ).fetchone()
    return row[0]


def test_record_completion_first_insert_creates_single_row(proxy):
    """First record_completion for a slug inserts exactly one row (AC7)."""
    proxy.record_completion(
        slug=UPSERT_SLUG,
        item_type=UPSERT_ITEM_TYPE,
        outcome="warn",
        cost_usd=1.23,
        duration_s=60.0,
        run_id=UPSERT_RUN_ID_1,
        tokens_per_minute=1500.0,
        verification_notes=UPSERT_NOTES_1,
    )

    assert _count_completion_rows(proxy, UPSERT_SLUG) == 1


def test_record_completion_first_insert_initializes_attempts_history(proxy):
    """First insert creates attempts_history with a single-entry JSON array (AC16, AC18)."""
    proxy.record_completion(
        slug=UPSERT_SLUG,
        item_type=UPSERT_ITEM_TYPE,
        outcome="warn",
        cost_usd=1.23,
        duration_s=60.0,
        run_id=UPSERT_RUN_ID_1,
        tokens_per_minute=1500.0,
        verification_notes=UPSERT_NOTES_1,
    )

    row = _read_completion_row(proxy, UPSERT_SLUG)
    history = json.loads(row["attempts_history"])
    assert isinstance(history, list)
    assert len(history) == 1

    entry = history[0]
    assert entry["outcome"] == "warn"
    assert abs(entry["cost_usd"] - 1.23) < 1e-9
    assert abs(entry["duration_s"] - 60.0) < 1e-9
    assert entry["run_id"] == UPSERT_RUN_ID_1
    assert abs(entry["tokens_per_minute"] - 1500.0) < 1e-9
    assert "finished_at" in entry


def test_record_completion_retry_only_one_row(proxy):
    """After a retry, exactly one row exists for the slug (AC1, AC2)."""
    proxy.record_completion(
        slug=UPSERT_SLUG,
        item_type=UPSERT_ITEM_TYPE,
        outcome="warn",
        cost_usd=1.23,
        duration_s=60.0,
        run_id=UPSERT_RUN_ID_1,
    )
    proxy.record_completion(
        slug=UPSERT_SLUG,
        item_type=UPSERT_ITEM_TYPE,
        outcome="success",
        cost_usd=0.50,
        duration_s=30.0,
        run_id=UPSERT_RUN_ID_2,
    )

    assert _count_completion_rows(proxy, UPSERT_SLUG) == 1


def test_record_completion_retry_accumulates_cost(proxy):
    """Second completion accumulates cost_usd by summing both attempts (AC8)."""
    proxy.record_completion(
        slug=UPSERT_SLUG, item_type=UPSERT_ITEM_TYPE, outcome="warn",
        cost_usd=1.23, duration_s=60.0,
    )
    proxy.record_completion(
        slug=UPSERT_SLUG, item_type=UPSERT_ITEM_TYPE, outcome="success",
        cost_usd=0.50, duration_s=30.0,
    )

    row = _read_completion_row(proxy, UPSERT_SLUG)
    assert abs(row["cost_usd"] - 1.73) < 1e-9


def test_record_completion_retry_accumulates_duration(proxy):
    """Second completion accumulates duration_s by summing both attempts (AC9)."""
    proxy.record_completion(
        slug=UPSERT_SLUG, item_type=UPSERT_ITEM_TYPE, outcome="warn",
        cost_usd=1.23, duration_s=60.0,
    )
    proxy.record_completion(
        slug=UPSERT_SLUG, item_type=UPSERT_ITEM_TYPE, outcome="success",
        cost_usd=0.50, duration_s=30.0,
    )

    row = _read_completion_row(proxy, UPSERT_SLUG)
    assert abs(row["duration_s"] - 90.0) < 1e-9


def test_record_completion_retry_replaces_outcome(proxy):
    """Second completion sets outcome to the latest attempt's value (AC10)."""
    proxy.record_completion(
        slug=UPSERT_SLUG, item_type=UPSERT_ITEM_TYPE, outcome="warn",
        cost_usd=1.23, duration_s=60.0,
    )
    proxy.record_completion(
        slug=UPSERT_SLUG, item_type=UPSERT_ITEM_TYPE, outcome="success",
        cost_usd=0.50, duration_s=30.0,
    )

    row = _read_completion_row(proxy, UPSERT_SLUG)
    assert row["outcome"] == "success"


def test_record_completion_retry_replaces_run_id(proxy):
    """Second completion sets run_id to the latest attempt's value (AC12)."""
    proxy.record_completion(
        slug=UPSERT_SLUG, item_type=UPSERT_ITEM_TYPE, outcome="warn",
        cost_usd=1.23, duration_s=60.0, run_id=UPSERT_RUN_ID_1,
    )
    proxy.record_completion(
        slug=UPSERT_SLUG, item_type=UPSERT_ITEM_TYPE, outcome="success",
        cost_usd=0.50, duration_s=30.0, run_id=UPSERT_RUN_ID_2,
    )

    row = _read_completion_row(proxy, UPSERT_SLUG)
    assert row["run_id"] == UPSERT_RUN_ID_2


def test_record_completion_retry_replaces_tokens_per_minute(proxy):
    """Second completion sets tokens_per_minute to the latest attempt's value (AC13)."""
    proxy.record_completion(
        slug=UPSERT_SLUG, item_type=UPSERT_ITEM_TYPE, outcome="warn",
        cost_usd=1.0, duration_s=60.0, tokens_per_minute=1000.0,
    )
    proxy.record_completion(
        slug=UPSERT_SLUG, item_type=UPSERT_ITEM_TYPE, outcome="success",
        cost_usd=0.5, duration_s=30.0, tokens_per_minute=2000.0,
    )

    row = _read_completion_row(proxy, UPSERT_SLUG)
    assert abs(row["tokens_per_minute"] - 2000.0) < 1e-9


def test_record_completion_retry_replaces_verification_notes(proxy):
    """Second completion sets verification_notes to the latest attempt's value (AC14)."""
    proxy.record_completion(
        slug=UPSERT_SLUG, item_type=UPSERT_ITEM_TYPE, outcome="warn",
        cost_usd=1.0, duration_s=60.0, verification_notes=UPSERT_NOTES_1,
    )
    proxy.record_completion(
        slug=UPSERT_SLUG, item_type=UPSERT_ITEM_TYPE, outcome="success",
        cost_usd=0.5, duration_s=30.0, verification_notes=UPSERT_NOTES_2,
    )

    row = _read_completion_row(proxy, UPSERT_SLUG)
    assert row["verification_notes"] == UPSERT_NOTES_2


def test_record_completion_retry_appends_to_attempts_history(proxy):
    """Second completion appends a new entry to attempts_history (AC17)."""
    proxy.record_completion(
        slug=UPSERT_SLUG, item_type=UPSERT_ITEM_TYPE, outcome="warn",
        cost_usd=1.23, duration_s=60.0, run_id=UPSERT_RUN_ID_1,
    )
    proxy.record_completion(
        slug=UPSERT_SLUG, item_type=UPSERT_ITEM_TYPE, outcome="success",
        cost_usd=0.50, duration_s=30.0, run_id=UPSERT_RUN_ID_2,
    )

    row = _read_completion_row(proxy, UPSERT_SLUG)
    history = json.loads(row["attempts_history"])
    assert isinstance(history, list)
    assert len(history) == 2
    assert history[0]["outcome"] == "warn"
    assert history[0]["run_id"] == UPSERT_RUN_ID_1
    assert history[1]["outcome"] == "success"
    assert history[1]["run_id"] == UPSERT_RUN_ID_2


def test_record_completion_attempts_history_entries_have_required_fields(proxy):
    """Each entry in attempts_history contains all required fields (AC18)."""
    proxy.record_completion(
        slug=UPSERT_SLUG, item_type=UPSERT_ITEM_TYPE, outcome="warn",
        cost_usd=1.23, duration_s=60.0, run_id=UPSERT_RUN_ID_1,
        tokens_per_minute=1500.0,
    )

    row = _read_completion_row(proxy, UPSERT_SLUG)
    history = json.loads(row["attempts_history"])
    entry = history[0]
    for field in ("outcome", "cost_usd", "duration_s", "finished_at", "run_id", "tokens_per_minute"):
        assert field in entry, f"Missing field: {field}"


def test_unique_constraint_on_slug_raises_on_raw_insert(proxy):
    """A raw INSERT with duplicate slug raises IntegrityError (AC3, AC4)."""
    proxy.record_completion(
        slug=UPSERT_SLUG, item_type=UPSERT_ITEM_TYPE, outcome="success",
        cost_usd=1.0, duration_s=10.0,
    )

    with pytest.raises(sqlite3.IntegrityError):
        with sqlite3.connect(str(proxy._db_path)) as conn:
            conn.execute(
                "INSERT INTO completions (slug, item_type, outcome, cost_usd, duration_s, finished_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                [UPSERT_SLUG, "feature", "fail", 0.5, 5.0, "2026-03-31T10:00:00"],
            )


# ─── Migration Tests (AC19–AC26) ─────────────────────────────────────────────

MIGRATION_SCHEMA_SQL = """
CREATE TABLE completions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL,
    item_type TEXT NOT NULL,
    outcome TEXT NOT NULL,
    cost_usd REAL NOT NULL DEFAULT 0.0,
    duration_s REAL NOT NULL DEFAULT 0.0,
    finished_at TEXT NOT NULL,
    run_id TEXT,
    tokens_per_minute REAL NOT NULL DEFAULT 0.0,
    verification_notes TEXT
)
"""

MIGRATION_OTHER_TABLES_SQL = [
    """CREATE TABLE traces (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL,
        parent_run_id TEXT,
        name TEXT NOT NULL,
        model TEXT NOT NULL DEFAULT '',
        start_time TEXT,
        end_time TEXT,
        inputs_json TEXT,
        outputs_json TEXT,
        metadata_json TEXT,
        error TEXT,
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE cost_tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_slug TEXT NOT NULL,
        item_type TEXT NOT NULL,
        task_id TEXT NOT NULL,
        agent_type TEXT NOT NULL,
        model TEXT NOT NULL,
        input_tokens INTEGER NOT NULL DEFAULT 0,
        output_tokens INTEGER NOT NULL DEFAULT 0,
        cost_usd REAL NOT NULL DEFAULT 0.0,
        duration_s REAL NOT NULL DEFAULT 0.0,
        tool_calls_json TEXT,
        recorded_at TEXT NOT NULL
    )""",
    """CREATE TABLE sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        label TEXT,
        start_time TEXT NOT NULL,
        end_time TEXT,
        total_cost_usd REAL NOT NULL DEFAULT 0.0,
        items_processed INTEGER NOT NULL DEFAULT 0,
        notes TEXT
    )""",
]


def _make_pre_migration_db(tmp_path, rows: list) -> str:
    """Create a SQLite DB with duplicate completion rows (no UNIQUE constraint, no attempts_history).

    Args:
        tmp_path: pytest tmp_path fixture.
        rows: List of (slug, item_type, outcome, cost_usd, duration_s, finished_at, run_id,
                       tokens_per_minute, verification_notes) tuples.

    Returns:
        Absolute path to the DB file as a string.
    """
    db_path = str(tmp_path / "pre-migration.db")
    with sqlite3.connect(db_path) as conn:
        conn.execute(MIGRATION_SCHEMA_SQL)
        for sql in MIGRATION_OTHER_TABLES_SQL:
            conn.execute(sql)
        for row in rows:
            conn.execute(
                "INSERT INTO completions"
                " (slug, item_type, outcome, cost_usd, duration_s, finished_at,"
                "  run_id, tokens_per_minute, verification_notes)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                row,
            )
    return db_path


def test_migration_merges_three_duplicate_rows_cost(tmp_path):
    """Migration sums cost_usd across all 3 rows for a duplicate slug (AC19)."""
    rows = [
        ("dup-slug", "feature", "warn", 1.0, 30.0, "2026-03-31T08:00:00", "run-1", 1000.0, None),
        ("dup-slug", "feature", "warn", 2.0, 60.0, "2026-03-31T09:00:00", "run-2", 1200.0, None),
        ("dup-slug", "feature", "success", 0.5, 15.0, "2026-03-31T10:00:00", "run-3", 1500.0, None),
    ]
    db_path = _make_pre_migration_db(tmp_path, rows)
    proxy = TracingProxy({"db_path": db_path})

    row = _read_completion_row(proxy, "dup-slug")
    assert abs(row["cost_usd"] - 3.5) < 1e-9


def test_migration_merges_three_duplicate_rows_duration(tmp_path):
    """Migration sums duration_s across all 3 rows for a duplicate slug (AC20)."""
    rows = [
        ("dup-slug", "feature", "warn", 1.0, 30.0, "2026-03-31T08:00:00", "run-1", 1000.0, None),
        ("dup-slug", "feature", "warn", 2.0, 60.0, "2026-03-31T09:00:00", "run-2", 1200.0, None),
        ("dup-slug", "feature", "success", 0.5, 15.0, "2026-03-31T10:00:00", "run-3", 1500.0, None),
    ]
    db_path = _make_pre_migration_db(tmp_path, rows)
    proxy = TracingProxy({"db_path": db_path})

    row = _read_completion_row(proxy, "dup-slug")
    assert abs(row["duration_s"] - 105.0) < 1e-9


def test_migration_merges_duplicate_rows_latest_fields(tmp_path):
    """Migration uses outcome/finished_at/run_id/tpm/notes from the latest row (AC21)."""
    notes_latest = '{"verdict": "success"}'
    rows = [
        ("dup-slug", "feature", "warn", 1.0, 30.0, "2026-03-31T08:00:00", "run-1", 1000.0, None),
        ("dup-slug", "feature", "success", 0.5, 15.0, "2026-03-31T10:00:00", "run-3", 1500.0, notes_latest),
        ("dup-slug", "feature", "warn", 2.0, 60.0, "2026-03-31T09:00:00", "run-2", 1200.0, None),
    ]
    db_path = _make_pre_migration_db(tmp_path, rows)
    proxy = TracingProxy({"db_path": db_path})

    row = _read_completion_row(proxy, "dup-slug")
    assert row["outcome"] == "success"
    assert row["finished_at"] == "2026-03-31T10:00:00"
    assert row["run_id"] == "run-3"
    assert abs(row["tokens_per_minute"] - 1500.0) < 1e-9
    assert row["verification_notes"] == notes_latest


def test_migration_builds_attempts_history_from_all_rows(tmp_path):
    """Migration builds attempts_history JSON array from all rows ordered by finished_at (AC22)."""
    rows = [
        ("dup-slug", "feature", "warn", 1.0, 30.0, "2026-03-31T08:00:00", "run-1", 1000.0, None),
        ("dup-slug", "feature", "warn", 2.0, 60.0, "2026-03-31T09:00:00", "run-2", 1200.0, None),
        ("dup-slug", "feature", "success", 0.5, 15.0, "2026-03-31T10:00:00", "run-3", 1500.0, None),
    ]
    db_path = _make_pre_migration_db(tmp_path, rows)
    proxy = TracingProxy({"db_path": db_path})

    row = _read_completion_row(proxy, "dup-slug")
    history = json.loads(row["attempts_history"])
    assert isinstance(history, list)
    assert len(history) == 3
    assert history[0]["run_id"] == "run-1"
    assert history[0]["finished_at"] == "2026-03-31T08:00:00"
    assert history[1]["run_id"] == "run-2"
    assert history[2]["run_id"] == "run-3"
    assert history[2]["finished_at"] == "2026-03-31T10:00:00"


def test_migration_deletes_extra_rows(tmp_path):
    """Migration deletes all but the merged row, leaving exactly one per slug (AC23)."""
    rows = [
        ("dup-slug", "feature", "warn", 1.0, 30.0, "2026-03-31T08:00:00", "run-1", 1000.0, None),
        ("dup-slug", "feature", "success", 0.5, 15.0, "2026-03-31T10:00:00", "run-2", 1500.0, None),
    ]
    db_path = _make_pre_migration_db(tmp_path, rows)
    proxy = TracingProxy({"db_path": db_path})

    with sqlite3.connect(db_path) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM completions WHERE slug = ?", ["dup-slug"]
        ).fetchone()[0]
    assert count == 1


def test_migration_handles_single_row_without_error(tmp_path):
    """Migration is a no-op for slugs that already have only one row (AC24)."""
    rows = [
        ("solo-slug", "feature", "success", 1.0, 30.0, "2026-03-31T08:00:00", "run-1", 1000.0, None),
    ]
    db_path = _make_pre_migration_db(tmp_path, rows)
    proxy = TracingProxy({"db_path": db_path})

    row = _read_completion_row(proxy, "solo-slug")
    assert abs(row["cost_usd"] - 1.0) < 1e-9

    history = json.loads(row["attempts_history"])
    assert len(history) == 1


def test_migration_is_idempotent(tmp_path):
    """Running _init_db a second time on the same DB does not alter data (idempotent)."""
    rows = [
        ("dup-slug", "feature", "warn", 1.0, 30.0, "2026-03-31T08:00:00", "run-1", 1000.0, None),
        ("dup-slug", "feature", "success", 0.5, 15.0, "2026-03-31T10:00:00", "run-2", 1500.0, None),
    ]
    db_path = _make_pre_migration_db(tmp_path, rows)
    proxy = TracingProxy({"db_path": db_path})

    # Record the merged state
    first_row = _read_completion_row(proxy, "dup-slug")

    # Create a second proxy pointing at the same DB — triggers _init_db again
    proxy2 = TracingProxy({"db_path": db_path})
    second_row = _read_completion_row(proxy2, "dup-slug")

    assert abs(second_row["cost_usd"] - first_row["cost_usd"]) < 1e-9
    assert abs(second_row["duration_s"] - first_row["duration_s"]) < 1e-9
    assert second_row["outcome"] == first_row["outcome"]

    history = json.loads(second_row["attempts_history"])
    assert len(history) == 2


def test_migration_runs_in_proxy_init_db(tmp_path):
    """Migration is executed inside proxy.py _init_db (AC26)."""
    rows = [
        ("slug-x", "defect", "warn", 0.8, 20.0, "2026-03-31T07:00:00", "run-a", 800.0, None),
        ("slug-x", "defect", "fail", 0.4, 10.0, "2026-03-31T08:00:00", "run-b", 900.0, None),
    ]
    db_path = _make_pre_migration_db(tmp_path, rows)

    # The TracingProxy constructor calls _init_db which must run the migration
    TracingProxy({"db_path": db_path})

    with sqlite3.connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM completions").fetchone()[0]
    assert count == 1, "Migration should have merged duplicates into one row"


def test_completions_table_has_attempts_history_column(proxy):
    """The completions table schema includes an attempts_history column (AC15)."""
    with sqlite3.connect(str(proxy._db_path)) as conn:
        info = conn.execute("PRAGMA table_info(completions)").fetchall()
    column_names = [row[1] for row in info]
    assert "attempts_history" in column_names

