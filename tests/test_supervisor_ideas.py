# tests/test_supervisor_ideas.py
# Tests that process_ideas() is called in the supervisor iteration loop.
# Design: docs/plans/2026-03-25-ideas-intake-pipeline-design.md

"""Verify that run_supervisor_loop() invokes process_ideas() on each iteration."""

import threading
from unittest.mock import MagicMock, patch

import langgraph_pipeline.supervisor as supervisor_mod


def test_supervisor_calls_process_ideas():
    """process_ideas is called at least once during a supervisor loop iteration."""
    shutdown_event = threading.Event()
    call_log: list[bool] = []

    def fake_process_ideas(dry_run: bool) -> int:
        call_log.append(dry_run)
        shutdown_event.set()  # stop after first iteration
        return 0

    with patch.object(supervisor_mod, "process_ideas", side_effect=fake_process_ideas):
        with patch.object(supervisor_mod, "_unclaim_orphaned_items"):
            with patch.object(supervisor_mod, "_reap_finished_workers", return_value=False):
                with patch.object(supervisor_mod, "_try_dispatch_one", return_value=False):
                    supervisor_mod.run_supervisor_loop(
                        max_workers=1,
                        budget_cap_usd=None,
                        dry_run=False,
                        shutdown_event=shutdown_event,
                        slack=None,
                    )

    assert len(call_log) >= 1, "process_ideas was not called"
    assert call_log[0] is False


def test_supervisor_passes_dry_run_flag():
    """process_ideas receives the dry_run flag from run_supervisor_loop."""
    shutdown_event = threading.Event()
    captured: list[bool] = []

    def fake_process_ideas(dry_run: bool) -> int:
        captured.append(dry_run)
        shutdown_event.set()
        return 0

    with patch.object(supervisor_mod, "process_ideas", side_effect=fake_process_ideas):
        with patch.object(supervisor_mod, "_unclaim_orphaned_items"):
            with patch.object(supervisor_mod, "_reap_finished_workers", return_value=False):
                with patch.object(supervisor_mod, "_try_dispatch_one", return_value=False):
                    supervisor_mod.run_supervisor_loop(
                        max_workers=1,
                        budget_cap_usd=None,
                        dry_run=False,
                        shutdown_event=shutdown_event,
                        slack=None,
                    )

    assert captured[0] is False


def test_supervisor_logs_ideas_processed(caplog):
    """A non-zero return from process_ideas triggers an info log entry."""
    import logging

    shutdown_event = threading.Event()
    call_count = 0

    def fake_process_ideas(dry_run: bool) -> int:
        nonlocal call_count
        call_count += 1
        shutdown_event.set()
        return 2  # simulate 2 ideas processed

    with caplog.at_level(logging.INFO, logger="langgraph_pipeline.supervisor"):
        with patch.object(supervisor_mod, "process_ideas", side_effect=fake_process_ideas):
            with patch.object(supervisor_mod, "_unclaim_orphaned_items"):
                with patch.object(supervisor_mod, "_reap_finished_workers", return_value=False):
                    with patch.object(supervisor_mod, "_try_dispatch_one", return_value=False):
                        supervisor_mod.run_supervisor_loop(
                            max_workers=1,
                            budget_cap_usd=None,
                            dry_run=False,
                            shutdown_event=shutdown_event,
                            slack=None,
                        )

    assert any("2 idea(s)" in r.message for r in caplog.records)
