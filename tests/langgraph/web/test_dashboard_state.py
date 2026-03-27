# tests/langgraph/web/test_dashboard_state.py
# Unit tests for DashboardState and its module-level singleton helpers.
# Design: docs/plans/2026-03-25-15-pipeline-activity-dashboard-design.md
# Design: docs/plans/2026-03-26-10-error-stream-always-empty-design.md
# Design: docs/plans/2026-03-27-03-dashboard-items-stuck-running-design.md

"""Unit tests for langgraph_pipeline.web.dashboard_state."""

import logging
import threading
import time

import pytest

import langgraph_pipeline.web.dashboard_state as ds_module
from langgraph_pipeline.web.dashboard_state import (
    MAX_RECENT_COMPLETIONS,
    MAX_RECENT_ERRORS,
    DashboardErrorHandler,
    DashboardState,
    get_dashboard_state,
    reset_dashboard_state,
)

# ─── Constants ────────────────────────────────────────────────────────────────

SAMPLE_PID = 12345
SAMPLE_SLUG = "defect-01-sample-bug"
SAMPLE_ITEM_TYPE = "defect"
SAMPLE_OUTCOME = "success"
SAMPLE_COST_USD = 0.05
SAMPLE_DURATION_S = 30.0

# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def fresh_state():
    """Reset the module-level singleton before every test."""
    reset_dashboard_state()
    yield
    reset_dashboard_state()


# ─── DashboardState Unit Tests ────────────────────────────────────────────────


def test_add_and_remove_active_worker():
    """add_active_worker then remove_active_worker leaves empty active_workers
    and one CompletionRecord in recent_completions with the expected outcome."""
    state = get_dashboard_state()

    state.add_active_worker(
        pid=SAMPLE_PID,
        slug=SAMPLE_SLUG,
        item_type=SAMPLE_ITEM_TYPE,
        start_time=time.monotonic(),
    )
    assert SAMPLE_PID in state.active_workers

    state.remove_active_worker(
        pid=SAMPLE_PID,
        outcome=SAMPLE_OUTCOME,
        cost_usd=SAMPLE_COST_USD,
        duration_s=SAMPLE_DURATION_S,
    )

    assert state.active_workers == {}
    assert len(state.recent_completions) == 1
    record = state.recent_completions[0]
    assert record.slug == SAMPLE_SLUG
    assert record.outcome == SAMPLE_OUTCOME


def test_completions_capped_at_max():
    """Adding MAX_RECENT_COMPLETIONS+1 completions keeps the list at MAX_RECENT_COMPLETIONS."""
    state = get_dashboard_state()

    for i in range(MAX_RECENT_COMPLETIONS + 1):
        pid = 10000 + i
        state.add_active_worker(
            pid=pid,
            slug=f"item-{i}",
            item_type="feature",
            start_time=time.monotonic(),
        )
        state.remove_active_worker(
            pid=pid,
            outcome="success",
            cost_usd=0.01,
            duration_s=1.0,
        )

    assert len(state.recent_completions) == MAX_RECENT_COMPLETIONS


def test_errors_capped_at_max():
    """Adding MAX_RECENT_ERRORS+1 errors keeps the list at MAX_RECENT_ERRORS."""
    state = get_dashboard_state()

    for i in range(MAX_RECENT_ERRORS + 1):
        state.add_error(f"error message {i}")

    assert len(state.recent_errors) == MAX_RECENT_ERRORS


def test_snapshot_returns_serialisable_dict():
    """snapshot() returns a dict containing all required top-level keys."""
    state = get_dashboard_state()

    result = state.snapshot()

    expected_keys = {
        "active_workers",
        "recent_completions",
        "queue_count",
        "session_cost_usd",
        "session_elapsed_s",
        "active_count",
        "total_processed",
        "recent_errors",
    }
    assert expected_keys == set(result.keys())
    # Verify the values are primitive-safe types (no dataclass instances)
    import json
    json.dumps(result)  # raises if not serialisable


def test_reset_clears_state():
    """reset_dashboard_state() replaces the singleton with a clean instance."""
    state = get_dashboard_state()
    state.add_active_worker(
        pid=SAMPLE_PID,
        slug=SAMPLE_SLUG,
        item_type=SAMPLE_ITEM_TYPE,
        start_time=time.monotonic(),
    )
    state.add_error("some error")

    reset_dashboard_state()

    new_state = get_dashboard_state()
    assert new_state is not state
    assert new_state.active_workers == {}
    assert new_state.recent_completions == []
    assert new_state.recent_errors == []


# ─── DashboardErrorHandler Tests ─────────────────────────────────────────────


def test_handler_forwards_warning_record():
    """DashboardErrorHandler.emit() adds WARNING records to recent_errors."""
    handler = DashboardErrorHandler()
    record = logging.LogRecord(
        name="langgraph_pipeline.test",
        level=logging.WARNING,
        pathname="",
        lineno=0,
        msg="something went wrong",
        args=(),
        exc_info=None,
    )

    handler.emit(record)

    state = get_dashboard_state()
    assert len(state.recent_errors) == 1
    assert "[WARNING]" in state.recent_errors[0]
    assert "langgraph_pipeline.test" in state.recent_errors[0]
    assert "something went wrong" in state.recent_errors[0]


def test_handler_forwards_error_record():
    """DashboardErrorHandler.emit() adds ERROR records to recent_errors."""
    handler = DashboardErrorHandler()
    record = logging.LogRecord(
        name="langgraph_pipeline.supervisor",
        level=logging.ERROR,
        pathname="",
        lineno=0,
        msg="worker crashed",
        args=(),
        exc_info=None,
    )

    handler.emit(record)

    state = get_dashboard_state()
    assert len(state.recent_errors) == 1
    assert "[ERROR]" in state.recent_errors[0]
    assert "worker crashed" in state.recent_errors[0]


def test_handler_ignores_debug_record():
    """DashboardErrorHandler filters DEBUG records even when the logger is at DEBUG level.

    This verifies that the handler's own setLevel(WARNING) prevents DEBUG records
    from reaching the error stream regardless of the logger's effective level —
    the scenario that occurs when --verbose is used.
    """
    test_logger = logging.getLogger("langgraph_pipeline._test_debug_filter")
    test_logger.setLevel(logging.DEBUG)
    handler = DashboardErrorHandler()
    test_logger.addHandler(handler)
    try:
        test_logger.debug("this should be filtered by the handler")
    finally:
        test_logger.removeHandler(handler)
        test_logger.setLevel(logging.NOTSET)

    assert get_dashboard_state().recent_errors == []


def test_handler_ignores_info_record():
    """DashboardErrorHandler filters INFO records even when the logger is at DEBUG level."""
    test_logger = logging.getLogger("langgraph_pipeline._test_info_filter")
    test_logger.setLevel(logging.DEBUG)
    handler = DashboardErrorHandler()
    test_logger.addHandler(handler)
    try:
        test_logger.info("this is informational")
    finally:
        test_logger.removeHandler(handler)
        test_logger.setLevel(logging.NOTSET)

    assert get_dashboard_state().recent_errors == []


def test_handler_accumulates_multiple_records():
    """Multiple emit() calls accumulate in recent_errors in LIFO order."""
    handler = DashboardErrorHandler()
    messages = ["first warning", "second warning", "third error"]
    levels = [logging.WARNING, logging.WARNING, logging.ERROR]

    for msg, level in zip(messages, levels):
        record = logging.LogRecord(
            name="langgraph_pipeline.node",
            level=level,
            pathname="",
            lineno=0,
            msg=msg,
            args=(),
            exc_info=None,
        )
        handler.emit(record)

    state = get_dashboard_state()
    assert len(state.recent_errors) == 3
    # add_error prepends, so most-recent is first
    assert "third error" in state.recent_errors[0]
    assert "second warning" in state.recent_errors[1]
    assert "first warning" in state.recent_errors[2]


def test_update_worker_run_id_sets_run_id():
    """update_worker_run_id sets run_id on a worker that was registered without one."""
    state = get_dashboard_state()
    state.add_active_worker(
        pid=SAMPLE_PID,
        slug=SAMPLE_SLUG,
        item_type=SAMPLE_ITEM_TYPE,
        start_time=time.monotonic(),
        run_id=None,
    )
    assert state.active_workers[SAMPLE_PID].run_id is None

    state.update_worker_run_id(SAMPLE_PID, "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")

    assert state.active_workers[SAMPLE_PID].run_id == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def test_update_worker_run_id_noop_for_unknown_pid():
    """update_worker_run_id is a no-op when the pid is not in active_workers."""
    state = get_dashboard_state()

    # Should not raise even when the pid is unknown.
    state.update_worker_run_id(99999, "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")

    assert state.active_workers == {}


def test_update_worker_run_id_snapshot_includes_run_id(monkeypatch):
    """snapshot() reflects the updated run_id after update_worker_run_id is called."""
    monkeypatch.setattr(
        "langgraph_pipeline.web.dashboard_state.get_proxy", lambda: None
    )
    # Prevent sweep_dead_workers from removing the fake PID.
    monkeypatch.setattr("langgraph_pipeline.web.dashboard_state.os.kill", lambda pid, sig: None)
    state = get_dashboard_state()
    state.add_active_worker(
        pid=SAMPLE_PID,
        slug=SAMPLE_SLUG,
        item_type=SAMPLE_ITEM_TYPE,
        start_time=time.monotonic(),
        run_id=None,
    )

    state.update_worker_run_id(SAMPLE_PID, "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")

    snap = state.snapshot()
    worker_snap = next(w for w in snap["active_workers"] if w["pid"] == SAMPLE_PID)
    assert worker_snap["run_id"] == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def test_thread_safety():
    """Concurrent add_active_worker and remove_active_worker must not raise and
    must leave the state in a consistent (no phantom workers) condition."""
    state = get_dashboard_state()
    barrier = threading.Barrier(2)
    exceptions: list[Exception] = []

    def writer():
        try:
            barrier.wait()
            for i in range(50):
                pid = 20000 + i
                state.add_active_worker(
                    pid=pid,
                    slug=f"concurrent-{i}",
                    item_type="defect",
                    start_time=time.monotonic(),
                )
                state.remove_active_worker(
                    pid=pid,
                    outcome="success",
                    cost_usd=0.001,
                    duration_s=0.1,
                )
        except Exception as exc:
            exceptions.append(exc)

    t1 = threading.Thread(target=writer)
    t2 = threading.Thread(target=writer)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert exceptions == [], f"Thread safety violation: {exceptions}"
    # All workers added were also removed, so active_workers must be empty
    assert state.active_workers == {}


# ─── Velocity tracking ──────────────────────────────────────────────────────


def test_worker_velocity_no_samples():
    """current_velocity returns 0.0 with fewer than 2 samples."""
    from langgraph_pipeline.web.dashboard_state import WorkerInfo
    w = WorkerInfo(pid=1, slug="test", item_type="feature", start_time=time.monotonic())
    assert w.current_velocity() == 0.0
    w.tokens_in = 500
    w.record_token_sample()
    assert w.current_velocity() == 0.0


def test_worker_velocity_two_samples():
    """current_velocity computes delta between last two samples."""
    from langgraph_pipeline.web.dashboard_state import WorkerInfo
    now = time.monotonic()
    w = WorkerInfo(pid=1, slug="test", item_type="feature", start_time=now)
    w.token_history.append((now, 0))
    w.token_history.append((now + 30, 3000))
    assert w.current_velocity() == 6000.0


def test_worker_velocity_series():
    """get_velocity_series returns per-interval velocities."""
    from langgraph_pipeline.web.dashboard_state import WorkerInfo
    now = time.monotonic()
    w = WorkerInfo(pid=1, slug="test", item_type="feature", start_time=now)
    w.token_history = [(now, 0), (now + 60, 1000), (now + 120, 4000)]
    series = w.get_velocity_series()
    assert len(series) == 2
    assert series[0][1] == 1000.0
    assert series[1][1] == 3000.0


def test_snapshot_includes_velocity(monkeypatch):
    """snapshot() includes tokens_per_minute and velocity_history."""
    from langgraph_pipeline.web.dashboard_state import DashboardState
    monkeypatch.setattr(
        "langgraph_pipeline.web.dashboard_state.get_proxy", lambda: None
    )
    state = DashboardState()
    # Disable sweep so fake PID isn't removed
    state.sweep_dead_workers = lambda: None
    now = time.monotonic()
    state.add_active_worker(pid=9999, slug="vel-test", item_type="feature", start_time=now)
    worker = state.active_workers[9999]
    worker.tokens_in = 2000
    worker.tokens_out = 1000
    worker.token_history = [(now, 0), (now + 60, 3000)]
    snap = state.snapshot()
    w_snap = next(w for w in snap["active_workers"] if w["pid"] == 9999)
    assert w_snap["tokens_per_minute"] == 3000.0
    assert len(w_snap["velocity_history"]) == 1
    state.remove_active_worker(9999, "success", 0.0, 1.0)


# ─── sweep_dead_workers Tests ─────────────────────────────────────────────────


def test_sweep_dead_workers_removes_dead_pid(monkeypatch):
    """sweep_dead_workers reaps a worker whose PID is no longer alive."""
    state = get_dashboard_state()
    state.add_active_worker(
        pid=SAMPLE_PID,
        slug=SAMPLE_SLUG,
        item_type=SAMPLE_ITEM_TYPE,
        start_time=time.monotonic(),
    )
    assert SAMPLE_PID in state.active_workers

    monkeypatch.setattr(
        "langgraph_pipeline.web.dashboard_state.os.kill",
        lambda pid, sig: (_ for _ in ()).throw(OSError("no such process")),
    )

    state.sweep_dead_workers()

    assert state.active_workers == {}
    assert len(state.recent_completions) == 1
    assert state.recent_completions[0].outcome == "fail"
    assert state.recent_completions[0].slug == SAMPLE_SLUG


def test_sweep_dead_workers_keeps_alive_pid(monkeypatch):
    """sweep_dead_workers does not remove a worker whose PID is still running."""
    state = get_dashboard_state()
    state.add_active_worker(
        pid=SAMPLE_PID,
        slug=SAMPLE_SLUG,
        item_type=SAMPLE_ITEM_TYPE,
        start_time=time.monotonic(),
    )

    monkeypatch.setattr(
        "langgraph_pipeline.web.dashboard_state.os.kill",
        lambda pid, sig: None,
    )

    state.sweep_dead_workers()

    assert SAMPLE_PID in state.active_workers
    assert state.recent_completions == []


def test_sweep_dead_workers_noop_when_empty():
    """sweep_dead_workers is a no-op when there are no active workers."""
    state = get_dashboard_state()
    assert state.active_workers == {}

    state.sweep_dead_workers()

    assert state.active_workers == {}
    assert state.recent_completions == []


def test_sweep_dead_workers_handles_pid_removed_between_probe_and_reap(monkeypatch):
    """sweep_dead_workers handles a TOCTOU race where the PID is removed by the
    normal reap path between the os.kill probe and the removal call."""
    state = get_dashboard_state()
    state.add_active_worker(
        pid=SAMPLE_PID,
        slug=SAMPLE_SLUG,
        item_type=SAMPLE_ITEM_TYPE,
        start_time=time.monotonic(),
    )

    original_remove = state.remove_active_worker

    def remove_and_then_kill(pid: int, sig: int) -> None:
        # Simulate: normal reap removes the worker just before sweep tries to
        original_remove(pid, "success", 0.01, 5.0)
        raise OSError("no such process")

    monkeypatch.setattr(
        "langgraph_pipeline.web.dashboard_state.os.kill",
        remove_and_then_kill,
    )

    # Should not raise; the TOCTOU guard (worker is None → continue) handles it
    state.sweep_dead_workers()

    assert state.active_workers == {}
    # The completion was recorded by the normal reap (outcome=success), not sweep
    assert len(state.recent_completions) == 1
    assert state.recent_completions[0].outcome == "success"


def test_snapshot_calls_sweep_dead_workers(monkeypatch):
    """snapshot() invokes sweep_dead_workers before building the active list."""
    monkeypatch.setattr(
        "langgraph_pipeline.web.dashboard_state.get_proxy", lambda: None
    )
    state = get_dashboard_state()
    sweep_calls: list[int] = []

    original_sweep = state.sweep_dead_workers

    def tracking_sweep() -> None:
        sweep_calls.append(1)
        original_sweep()

    state.sweep_dead_workers = tracking_sweep
    # Prevent real os.kill from probing non-existent PIDs during the sweep
    monkeypatch.setattr("langgraph_pipeline.web.dashboard_state.os.kill", lambda pid, sig: None)

    state.snapshot()

    assert len(sweep_calls) == 1
