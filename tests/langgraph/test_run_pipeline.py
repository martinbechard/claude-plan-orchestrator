# tests/langgraph/test_run_pipeline.py
# Unit tests for langgraph_pipeline/cli.py: CLI parsing, PID management, signal handling,
# budget enforcement, single-item mode, and scan loop.
# Design: docs/plans/2026-02-26-20-unified-langgraph-runner-design.md

"""Unit tests for the unified LangGraph pipeline runner (langgraph_pipeline.cli)."""

import logging
import os
import signal
import threading
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import langgraph_pipeline.cli as _mod
from langgraph_pipeline.cli import (
    EXIT_CODE_BUDGET_EXHAUSTED,
    EXIT_CODE_CLEAN,
    EXIT_CODE_ERROR,
    _build_arg_parser,
    _check_stale_pid,
    _is_budget_exhausted,
    _register_signal_handlers,
    _remove_pid_file,
    _run_scan_loop,
    _run_single_item,
    _write_pid_file,
)

# ─── Shared state helper ──────────────────────────────────────────────────────

_BASE_STATE: dict = {
    "item_path": "",
    "item_slug": "",
    "item_type": "feature",
    "item_name": "",
    "plan_path": None,
    "design_doc_path": None,
    "verification_cycle": 0,
    "verification_history": [],
    "should_stop": False,
    "rate_limited": False,
    "rate_limit_reset": None,
    "budget_cap_usd": None,
    "session_cost_usd": 0.0,
    "session_input_tokens": 0,
    "session_output_tokens": 0,
    "intake_count_defects": 0,
    "intake_count_features": 0,
}


def _make_state(**overrides) -> dict:
    """Return a minimal PipelineState-compatible dict with optional overrides."""
    return {**_BASE_STATE, **overrides}


# ─── CLI argument parsing ─────────────────────────────────────────────────────


class TestArgParsing:
    def test_defaults(self):
        args = _build_arg_parser().parse_args([])
        assert args.budget_cap is None
        assert args.dry_run is False
        assert args.single_item is None
        assert args.backlog_dir is None
        assert args.log_level == "INFO"
        assert args.no_slack is False
        assert args.no_tracing is False

    def test_budget_cap_float(self):
        args = _build_arg_parser().parse_args(["--budget-cap", "5.50"])
        assert args.budget_cap == pytest.approx(5.50)

    def test_dry_run_flag(self):
        args = _build_arg_parser().parse_args(["--dry-run"])
        assert args.dry_run is True

    def test_single_item_flag(self):
        args = _build_arg_parser().parse_args(
            ["--single-item", "docs/feature-backlog/42-foo.md"]
        )
        assert args.single_item == "docs/feature-backlog/42-foo.md"

    def test_backlog_dir_flag(self):
        args = _build_arg_parser().parse_args(["--backlog-dir", "/tmp/backlog"])
        assert args.backlog_dir == "/tmp/backlog"

    def test_log_level_debug(self):
        args = _build_arg_parser().parse_args(["--log-level", "DEBUG"])
        assert args.log_level == "DEBUG"

    def test_log_level_warning(self):
        args = _build_arg_parser().parse_args(["--log-level", "WARNING"])
        assert args.log_level == "WARNING"

    def test_log_level_error(self):
        args = _build_arg_parser().parse_args(["--log-level", "ERROR"])
        assert args.log_level == "ERROR"

    def test_no_slack_flag(self):
        args = _build_arg_parser().parse_args(["--no-slack"])
        assert args.no_slack is True

    def test_no_tracing_flag(self):
        args = _build_arg_parser().parse_args(["--no-tracing"])
        assert args.no_tracing is True

    def test_combined_flags(self):
        args = _build_arg_parser().parse_args(
            [
                "--budget-cap", "10.0",
                "--dry-run",
                "--no-slack",
                "--no-tracing",
                "--log-level", "ERROR",
            ]
        )
        assert args.budget_cap == pytest.approx(10.0)
        assert args.dry_run is True
        assert args.no_slack is True
        assert args.no_tracing is True
        assert args.log_level == "ERROR"

    def test_invalid_log_level_raises_system_exit(self):
        with pytest.raises(SystemExit):
            _build_arg_parser().parse_args(["--log-level", "VERBOSE"])

    def test_budget_cap_default_is_none(self):
        args = _build_arg_parser().parse_args([])
        assert args.budget_cap is None

    def test_single_item_and_backlog_dir_both_accepted(self):
        args = _build_arg_parser().parse_args(
            ["--single-item", "path/to/item.md", "--backlog-dir", "/alt/backlog"]
        )
        assert args.single_item == "path/to/item.md"
        assert args.backlog_dir == "/alt/backlog"


# ─── PID file lifecycle ───────────────────────────────────────────────────────


class TestPidFileLifecycle:
    def test_write_creates_file_with_current_pid(self, tmp_path):
        pid_file = str(tmp_path / ".lg-pipeline.pid")
        with patch.object(_mod, "LANGGRAPH_PID_FILE_PATH", pid_file):
            _write_pid_file()
        assert Path(pid_file).exists()
        assert int(Path(pid_file).read_text().strip()) == os.getpid()

    def test_remove_deletes_existing_file(self, tmp_path):
        pid_file = str(tmp_path / ".lg-pipeline.pid")
        Path(pid_file).write_text(str(os.getpid()))
        with patch.object(_mod, "LANGGRAPH_PID_FILE_PATH", pid_file):
            _remove_pid_file()
        assert not Path(pid_file).exists()

    def test_remove_tolerates_missing_file(self, tmp_path):
        pid_file = str(tmp_path / "nonexistent.pid")
        with patch.object(_mod, "LANGGRAPH_PID_FILE_PATH", pid_file):
            _remove_pid_file()  # Must not raise FileNotFoundError.

    def test_write_then_remove_full_lifecycle(self, tmp_path):
        pid_file = str(tmp_path / ".lg-pipeline.pid")
        with patch.object(_mod, "LANGGRAPH_PID_FILE_PATH", pid_file):
            _write_pid_file()
            assert Path(pid_file).exists()
            _remove_pid_file()
            assert not Path(pid_file).exists()

    def test_write_overwrites_stale_file(self, tmp_path):
        pid_file = str(tmp_path / ".lg-pipeline.pid")
        Path(pid_file).write_text("99999")
        with patch.object(_mod, "LANGGRAPH_PID_FILE_PATH", pid_file):
            _write_pid_file()
        assert int(Path(pid_file).read_text().strip()) == os.getpid()


# ─── Stale PID detection ──────────────────────────────────────────────────────


class TestStalePidDetection:
    def test_no_pid_file_returns_silently(self, tmp_path):
        pid_file = str(tmp_path / "absent.pid")
        with patch.object(_mod, "LANGGRAPH_PID_FILE_PATH", pid_file):
            _check_stale_pid()  # Must not raise.

    def test_stale_pid_dead_process_does_not_warn(self, tmp_path, caplog):
        """When the stored PID is dead (ProcessLookupError), only a debug is emitted."""
        pid_file = str(tmp_path / ".lg-pipeline.pid")
        Path(pid_file).write_text("99999999")
        with patch.object(_mod, "LANGGRAPH_PID_FILE_PATH", pid_file):
            with patch("os.kill", side_effect=ProcessLookupError):
                with caplog.at_level(logging.WARNING):
                    _check_stale_pid()
        # No warning should be emitted for a dead process.
        assert not any(r.levelno >= logging.WARNING for r in caplog.records)

    def test_alive_pid_emits_warning(self, tmp_path, caplog):
        """When the stored PID is alive (os.kill succeeds), a warning is emitted."""
        pid_file = str(tmp_path / ".lg-pipeline.pid")
        Path(pid_file).write_text(str(os.getpid()))
        with patch.object(_mod, "LANGGRAPH_PID_FILE_PATH", pid_file):
            with patch("os.kill", return_value=None):
                with caplog.at_level(logging.WARNING):
                    _check_stale_pid()
        assert any(r.levelno >= logging.WARNING for r in caplog.records)

    def test_permission_error_emits_warning(self, tmp_path, caplog):
        """When os.kill raises PermissionError, a warning is emitted."""
        pid_file = str(tmp_path / ".lg-pipeline.pid")
        Path(pid_file).write_text("12345")
        with patch.object(_mod, "LANGGRAPH_PID_FILE_PATH", pid_file):
            with patch("os.kill", side_effect=PermissionError):
                with caplog.at_level(logging.WARNING):
                    _check_stale_pid()
        assert any(r.levelno >= logging.WARNING for r in caplog.records)

    def test_unreadable_pid_file_returns_silently(self, tmp_path):
        """Non-integer content in PID file is silently ignored."""
        pid_file = str(tmp_path / ".lg-pipeline.pid")
        Path(pid_file).write_text("not-a-pid")
        with patch.object(_mod, "LANGGRAPH_PID_FILE_PATH", pid_file):
            _check_stale_pid()  # Must not raise.


# ─── Signal handler ───────────────────────────────────────────────────────────


class TestSignalHandler:
    """Signal handler tests: each test restores the previous handlers to avoid leaking."""

    def setup_method(self):
        self._prev_sigint = signal.getsignal(signal.SIGINT)
        self._prev_sigterm = signal.getsignal(signal.SIGTERM)

    def teardown_method(self):
        signal.signal(signal.SIGINT, self._prev_sigint)
        signal.signal(signal.SIGTERM, self._prev_sigterm)

    def test_sigint_sets_shutdown_event(self):
        shutdown_event = threading.Event()
        _register_signal_handlers(shutdown_event)
        os.kill(os.getpid(), signal.SIGINT)
        assert shutdown_event.is_set()

    def test_sigterm_sets_shutdown_event(self):
        shutdown_event = threading.Event()
        _register_signal_handlers(shutdown_event)
        os.kill(os.getpid(), signal.SIGTERM)
        assert shutdown_event.is_set()

    def test_handler_is_idempotent(self):
        """Sending the signal twice still results in the event being set."""
        shutdown_event = threading.Event()
        _register_signal_handlers(shutdown_event)
        os.kill(os.getpid(), signal.SIGINT)
        os.kill(os.getpid(), signal.SIGINT)
        assert shutdown_event.is_set()


# ─── Budget cap enforcement ───────────────────────────────────────────────────


class TestBudgetCapEnforcement:
    def test_no_cap_is_never_exhausted(self):
        state = _make_state(session_cost_usd=999.99)
        assert _is_budget_exhausted(state, None) is False

    def test_below_cap_is_not_exhausted(self):
        state = _make_state(session_cost_usd=4.99)
        assert _is_budget_exhausted(state, 5.0) is False

    def test_at_cap_is_exhausted(self):
        state = _make_state(session_cost_usd=5.0)
        assert _is_budget_exhausted(state, 5.0) is True

    def test_above_cap_is_exhausted(self):
        state = _make_state(session_cost_usd=6.0)
        assert _is_budget_exhausted(state, 5.0) is True

    def test_zero_cost_zero_cap_is_exhausted(self):
        state = _make_state(session_cost_usd=0.0)
        assert _is_budget_exhausted(state, 0.0) is True

    def test_missing_cost_field_treats_as_zero(self):
        """If session_cost_usd is absent, .get() returns 0.0 and cap is not exceeded."""
        state = {k: v for k, v in _BASE_STATE.items() if k != "session_cost_usd"}
        assert _is_budget_exhausted(state, 5.0) is False


# ─── Single-item mode ─────────────────────────────────────────────────────────


def _graph_cm_returning(state: dict):
    """Return a `pipeline_graph`-compatible context manager that yields one state."""
    mock_graph = MagicMock()
    mock_graph.invoke.return_value = state

    @contextmanager
    def _cm(*args, **kwargs):
        yield mock_graph

    return _cm, mock_graph


class TestSingleItemMode:
    def test_exits_0_on_success(self):
        state = _make_state(session_cost_usd=0.5)
        mock_cm, mock_graph = _graph_cm_returning(state)
        with patch.object(_mod, "pipeline_graph", mock_cm):
            code = _run_single_item("docs/feature-backlog/42-foo.md", None, False)
        assert code == EXIT_CODE_CLEAN

    def test_invokes_graph_exactly_once(self):
        state = _make_state(session_cost_usd=0.5)
        mock_cm, mock_graph = _graph_cm_returning(state)
        with patch.object(_mod, "pipeline_graph", mock_cm):
            _run_single_item("docs/feature-backlog/42-foo.md", None, False)
        mock_graph.invoke.assert_called_once()

    def test_sets_item_path_in_initial_state(self):
        state = _make_state(session_cost_usd=0.0)
        mock_cm, mock_graph = _graph_cm_returning(state)
        with patch.object(_mod, "pipeline_graph", mock_cm):
            _run_single_item("docs/feature-backlog/42-foo.md", None, False)
        initial_state = mock_graph.invoke.call_args[0][0]
        assert initial_state["item_path"] == "docs/feature-backlog/42-foo.md"

    def test_exits_2_when_budget_exceeded(self):
        state = _make_state(session_cost_usd=10.0)
        mock_cm, mock_graph = _graph_cm_returning(state)
        with patch.object(_mod, "pipeline_graph", mock_cm):
            code = _run_single_item("docs/feature-backlog/42-foo.md", 5.0, False)
        assert code == EXIT_CODE_BUDGET_EXHAUSTED

    def test_dry_run_skips_graph_and_exits_0(self):
        mock_cm = MagicMock()
        with patch.object(_mod, "pipeline_graph", mock_cm):
            code = _run_single_item("docs/feature-backlog/42-foo.md", None, True)
        assert code == EXIT_CODE_CLEAN
        mock_cm.assert_not_called()

    def test_exits_1_on_unhandled_exception(self):
        @contextmanager
        def _failing_cm(*args, **kwargs):
            mock_graph = MagicMock()
            mock_graph.invoke.side_effect = RuntimeError("graph failure")
            yield mock_graph

        with patch.object(_mod, "pipeline_graph", _failing_cm):
            code = _run_single_item("docs/feature-backlog/42-foo.md", None, False)
        assert code == EXIT_CODE_ERROR

    def test_budget_cap_embedded_in_initial_state(self):
        state = _make_state(session_cost_usd=0.0)
        mock_cm, mock_graph = _graph_cm_returning(state)
        with patch.object(_mod, "pipeline_graph", mock_cm):
            _run_single_item("docs/feature-backlog/42-foo.md", 7.5, False)
        initial_state = mock_graph.invoke.call_args[0][0]
        assert initial_state["budget_cap_usd"] == pytest.approx(7.5)


# ─── Scan loop ────────────────────────────────────────────────────────────────

_DUMMY_PRE_SCAN_STATE = _make_state(item_slug="item-x", item_path="docs/feature-backlog/1-x.md")


def _graph_cm_with_states(states: list):
    """Return a CM mock whose graph.invoke() returns successive states from the list."""
    mock_graph = MagicMock()
    mock_graph.invoke.side_effect = list(states)

    @contextmanager
    def _cm(*args, **kwargs):
        yield mock_graph

    return _cm, mock_graph


def _scan_loop_infra_patches(pre_scan_state=_DUMMY_PRE_SCAN_STATE):
    """Return a list of patch() context managers for all _run_scan_loop infrastructure.

    Patches _pre_scan, process_ideas, _reinstate_answered_suspensions,
    _post_pending_suspension_questions, and CodeChangeMonitor so tests
    run instantly without touching the real filesystem or waiting for
    SCAN_SLEEP_SECONDS.
    """
    mock_monitor = MagicMock()
    mock_monitor.restart_pending = MagicMock()
    mock_monitor.restart_pending.is_set.return_value = False
    return [
        patch.object(_mod, "_pre_scan", return_value=pre_scan_state),
        patch.object(_mod, "process_ideas", return_value=0),
        patch.object(_mod, "_reinstate_answered_suspensions"),
        patch.object(_mod, "_post_pending_suspension_questions"),
        patch.object(_mod, "CodeChangeMonitor", return_value=mock_monitor),
    ]


class TestScanLoop:
    def test_exits_2_when_first_invocation_exceeds_budget(self):
        states = [_make_state(session_cost_usd=6.0, item_slug="item-a")]
        mock_cm, mock_graph = _graph_cm_with_states(states)
        shutdown_event = threading.Event()
        patches = _scan_loop_infra_patches()
        with patch.object(_mod, "pipeline_graph", mock_cm):
            with patches[0], patches[1], patches[2], patches[3], patches[4]:
                code = _run_scan_loop(5.0, False, shutdown_event)
        assert code == EXIT_CODE_BUDGET_EXHAUSTED
        mock_graph.invoke.assert_called_once()

    def test_exits_2_on_second_invocation_exceeding_budget(self):
        """Budget is checked after each invocation; second call triggers cap."""
        states = [
            _make_state(session_cost_usd=3.0, item_slug="item-a"),
            _make_state(session_cost_usd=6.0, item_slug="item-b"),
        ]
        mock_cm, mock_graph = _graph_cm_with_states(states)
        shutdown_event = threading.Event()
        patches = _scan_loop_infra_patches()
        with patch.object(_mod, "pipeline_graph", mock_cm):
            with patches[0], patches[1], patches[2], patches[3], patches[4]:
                code = _run_scan_loop(5.0, False, shutdown_event)
        assert code == EXIT_CODE_BUDGET_EXHAUSTED
        assert mock_graph.invoke.call_count == 2

    def test_exits_0_when_shutdown_event_set_mid_loop(self):
        """Setting the shutdown event inside invoke() causes a clean exit."""
        shutdown_event = threading.Event()

        def _invoke_and_signal(state, *args, **kwargs):
            shutdown_event.set()
            return _make_state(session_cost_usd=0.1, item_slug="item-a")

        mock_graph = MagicMock()
        mock_graph.invoke.side_effect = _invoke_and_signal

        @contextmanager
        def _cm(*args, **kwargs):
            yield mock_graph

        patches = _scan_loop_infra_patches()
        with patch.object(_mod, "pipeline_graph", _cm):
            with patches[0], patches[1], patches[2], patches[3], patches[4]:
                code = _run_scan_loop(None, False, shutdown_event)
        assert code == EXIT_CODE_CLEAN

    def test_dry_run_exits_0_when_shutdown_set_immediately(self):
        """In dry-run, the loop checks shutdown_event; setting it exits cleanly."""
        shutdown_event = threading.Event()
        shutdown_event.set()
        code = _run_scan_loop(None, True, shutdown_event)
        assert code == EXIT_CODE_CLEAN

    def test_exits_1_on_unhandled_exception_in_loop(self):
        @contextmanager
        def _failing_cm(*args, **kwargs):
            mock_graph = MagicMock()
            mock_graph.invoke.side_effect = RuntimeError("boom")
            yield mock_graph

        shutdown_event = threading.Event()
        patches = _scan_loop_infra_patches()
        with patch.object(_mod, "pipeline_graph", _failing_cm):
            with patches[0], patches[1], patches[2], patches[3], patches[4]:
                code = _run_scan_loop(None, False, shutdown_event)
        assert code == EXIT_CODE_ERROR

    def test_no_budget_cap_loops_until_shutdown(self):
        """With no budget cap the loop only stops via the shutdown event."""
        shutdown_event = threading.Event()
        call_count = [0]

        def _invoke(state, *args, **kwargs):
            call_count[0] += 1
            if call_count[0] >= 3:
                shutdown_event.set()
            return _make_state(session_cost_usd=float(call_count[0]), item_slug="item")

        mock_graph = MagicMock()
        mock_graph.invoke.side_effect = _invoke

        @contextmanager
        def _cm(*args, **kwargs):
            yield mock_graph

        patches = _scan_loop_infra_patches()
        with patch.object(_mod, "pipeline_graph", _cm):
            with patches[0], patches[1], patches[2], patches[3], patches[4]:
                code = _run_scan_loop(None, False, shutdown_event)
        assert code == EXIT_CODE_CLEAN
        assert call_count[0] == 3
