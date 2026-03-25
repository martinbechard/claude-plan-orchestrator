# tests/langgraph/web/test_dashboard_state.py
# Unit tests for DashboardState and its module-level singleton helpers.
# Design: docs/plans/2026-03-25-15-pipeline-activity-dashboard-design.md

"""Unit tests for langgraph_pipeline.web.dashboard_state."""

import threading
import time

import pytest

import langgraph_pipeline.web.dashboard_state as ds_module
from langgraph_pipeline.web.dashboard_state import (
    MAX_RECENT_COMPLETIONS,
    MAX_RECENT_ERRORS,
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
