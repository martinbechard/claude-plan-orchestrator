# langgraph_pipeline/shared/hot_reload.py
# Hot-reload utilities: file-hash monitoring, change detection, and process restart.
# Design: docs/plans/2026-03-24-07-hot-reload-on-code-change-detection-design.md

"""Hot-reload utilities for the LangGraph pipeline.

Monitors watched source files for SHA-256 hash changes on a background daemon
thread. When a change is detected, sets a ``restart_pending`` event so the
main loop can restart cleanly between work items via ``os.execv``.
"""

import glob
import hashlib
import logging
import os
import sys
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

CODE_CHANGE_POLL_INTERVAL_SECONDS = 10

# All .py files under langgraph_pipeline/ plus the legacy wrapper script.
HOT_RELOAD_WATCHED_FILES: list[str] = sorted(
    glob.glob("langgraph_pipeline/**/*.py", recursive=True)
    + glob.glob("langgraph_pipeline/*.py")
    + ["scripts/auto-pipeline.py"]
)


# ─── Hash utilities ───────────────────────────────────────────────────────────


def _compute_file_hash(filepath: str) -> str:
    """Return the SHA-256 hex digest of *filepath*, or '' on I/O error."""
    try:
        with open(filepath, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()
    except OSError:
        return ""


def snapshot_source_hashes() -> dict[str, str]:
    """Return a mapping of each watched file path to its current SHA-256 hash."""
    return {path: _compute_file_hash(path) for path in HOT_RELOAD_WATCHED_FILES}


def check_code_changed(baseline: dict[str, str]) -> bool:
    """Return True if any watched file differs from *baseline*.

    A file is considered changed if its current hash differs from the
    baseline hash, including files that have been added or removed since
    the baseline was taken.
    """
    current = snapshot_source_hashes()
    return current != baseline


# ─── Background monitor ───────────────────────────────────────────────────────


class CodeChangeMonitor(threading.Thread):
    """Daemon thread that polls watched files and signals when code changes.

    Sets ``restart_pending`` when a hash change is detected. The caller is
    responsible for checking the event between work items and calling
    ``_perform_restart`` to restart the process cleanly.
    """

    def __init__(self, poll_interval: int = CODE_CHANGE_POLL_INTERVAL_SECONDS) -> None:
        super().__init__(name="CodeChangeMonitor", daemon=True)
        self.poll_interval = poll_interval
        self.restart_pending = threading.Event()
        self._stop_event = threading.Event()
        self._baseline: dict[str, str] = snapshot_source_hashes()

    def stop(self) -> None:
        """Signal the monitor thread to exit on its next poll cycle."""
        self._stop_event.set()

    def run(self) -> None:
        """Poll watched files until stopped or a change is detected."""
        while not self._stop_event.is_set():
            time.sleep(self.poll_interval)
            if self._stop_event.is_set():
                break
            if check_code_changed(self._baseline):
                logger.info("CodeChangeMonitor: source change detected, signalling restart")
                self.restart_pending.set()
                break


# ─── Restart ──────────────────────────────────────────────────────────────────


def _perform_restart(code_monitor: Optional[CodeChangeMonitor]) -> None:
    """Stop *code_monitor*, remove the PID file, and restart via os.execv.

    Replaces the current process in-place, preserving the PID so the PID
    file written at startup remains valid after the restart.
    """
    from langgraph_pipeline.shared.paths import LANGGRAPH_PID_FILE_PATH

    if code_monitor is not None:
        code_monitor.stop()

    try:
        os.remove(LANGGRAPH_PID_FILE_PATH)
    except OSError:
        pass

    logger.info("Restarting process due to code change: %s %s", sys.executable, sys.argv)
    os.execv(sys.executable, [sys.executable] + sys.argv)
