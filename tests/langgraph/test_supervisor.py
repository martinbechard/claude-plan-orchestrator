# tests/langgraph/test_supervisor.py
# Unit tests for supervisor helpers, focused on the run_id refresh mechanism.
# Design: docs/plans/2026-03-26-20-worker-trace-link-finds-nothing-design.md

"""Unit tests for langgraph_pipeline.supervisor._refresh_worker_run_ids."""

import time
from unittest.mock import patch

import pytest

from langgraph_pipeline.supervisor import WorkerRecord, _refresh_worker_run_ids
from langgraph_pipeline.web.dashboard_state import get_dashboard_state, reset_dashboard_state

# ─── Constants ────────────────────────────────────────────────────────────────

SAMPLE_PID = 12345
SAMPLE_SLUG = "defect-20-trace-fix"
SAMPLE_ITEM_TYPE = "defect"
SAMPLE_CLAIMED_PATH = "/tmp/claimed/defect-20-trace-fix.md"
SAMPLE_RESULT_FILE = "/tmp/worker-abc123.result.json"
SAMPLE_RUN_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def fresh_state():
    """Reset the DashboardState singleton before every test."""
    reset_dashboard_state()
    yield
    reset_dashboard_state()


def _make_worker_record(claimed_path: str = SAMPLE_CLAIMED_PATH) -> WorkerRecord:
    return (claimed_path, SAMPLE_RESULT_FILE, SAMPLE_ITEM_TYPE, time.monotonic())


# ─── _refresh_worker_run_ids Tests ────────────────────────────────────────────


def test_refresh_sets_run_id_when_file_has_trace():
    """_refresh_worker_run_ids updates run_id when read_trace_id_from_file returns a UUID."""
    state = get_dashboard_state()
    state.add_active_worker(
        pid=SAMPLE_PID,
        slug=SAMPLE_SLUG,
        item_type=SAMPLE_ITEM_TYPE,
        start_time=time.monotonic(),
        run_id=None,
    )
    active_workers: dict[int, WorkerRecord] = {SAMPLE_PID: _make_worker_record()}

    with patch(
        "langgraph_pipeline.supervisor.read_trace_id_from_file",
        return_value=SAMPLE_RUN_ID,
    ):
        _refresh_worker_run_ids(active_workers)

    assert state.active_workers[SAMPLE_PID].run_id == SAMPLE_RUN_ID


def test_refresh_skips_worker_when_file_has_no_trace():
    """_refresh_worker_run_ids leaves run_id as None when the file has no trace yet."""
    state = get_dashboard_state()
    state.add_active_worker(
        pid=SAMPLE_PID,
        slug=SAMPLE_SLUG,
        item_type=SAMPLE_ITEM_TYPE,
        start_time=time.monotonic(),
        run_id=None,
    )
    active_workers: dict[int, WorkerRecord] = {SAMPLE_PID: _make_worker_record()}

    with patch(
        "langgraph_pipeline.supervisor.read_trace_id_from_file",
        return_value=None,
    ):
        _refresh_worker_run_ids(active_workers)

    assert state.active_workers[SAMPLE_PID].run_id is None


def test_refresh_skips_worker_already_has_run_id():
    """_refresh_worker_run_ids does not call read_trace_id_from_file for workers that already have a run_id."""
    state = get_dashboard_state()
    state.add_active_worker(
        pid=SAMPLE_PID,
        slug=SAMPLE_SLUG,
        item_type=SAMPLE_ITEM_TYPE,
        start_time=time.monotonic(),
        run_id=SAMPLE_RUN_ID,
    )
    active_workers: dict[int, WorkerRecord] = {SAMPLE_PID: _make_worker_record()}

    with patch(
        "langgraph_pipeline.supervisor.read_trace_id_from_file",
        return_value="different-uuid",
    ) as mock_read:
        _refresh_worker_run_ids(active_workers)

    mock_read.assert_not_called()
    # run_id must remain unchanged
    assert state.active_workers[SAMPLE_PID].run_id == SAMPLE_RUN_ID


def test_refresh_handles_empty_active_workers():
    """_refresh_worker_run_ids is a no-op when no workers are active."""
    active_workers: dict[int, WorkerRecord] = {}

    with patch(
        "langgraph_pipeline.supervisor.read_trace_id_from_file"
    ) as mock_read:
        _refresh_worker_run_ids(active_workers)

    mock_read.assert_not_called()


def test_refresh_only_updates_workers_missing_run_id():
    """With multiple workers, only those with run_id=None are refreshed."""
    state = get_dashboard_state()
    pid_no_trace = 10001
    pid_has_trace = 10002
    existing_run_id = "11111111-2222-3333-4444-555555555555"

    state.add_active_worker(
        pid=pid_no_trace,
        slug="item-no-trace",
        item_type="feature",
        start_time=time.monotonic(),
        run_id=None,
    )
    state.add_active_worker(
        pid=pid_has_trace,
        slug="item-has-trace",
        item_type="feature",
        start_time=time.monotonic(),
        run_id=existing_run_id,
    )

    active_workers: dict[int, WorkerRecord] = {
        pid_no_trace: _make_worker_record("/tmp/item-no-trace.md"),
        pid_has_trace: _make_worker_record("/tmp/item-has-trace.md"),
    }

    with patch(
        "langgraph_pipeline.supervisor.read_trace_id_from_file",
        return_value=SAMPLE_RUN_ID,
    ) as mock_read:
        _refresh_worker_run_ids(active_workers)

    # Only the worker without a run_id should have been probed.
    mock_read.assert_called_once_with("/tmp/item-no-trace.md")
    assert state.active_workers[pid_no_trace].run_id == SAMPLE_RUN_ID
    assert state.active_workers[pid_has_trace].run_id == existing_run_id
