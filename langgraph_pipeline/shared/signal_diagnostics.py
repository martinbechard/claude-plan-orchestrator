# langgraph_pipeline/shared/signal_diagnostics.py
# Forensic diagnostics for unexpected signal delivery (SIGTERM/SIGINT).
# Captures process tree, open ports, stack traces, and caller context
# to identify the source of signals that kill the pipeline.

"""Signal diagnostics for the LangGraph pipeline.

When the pipeline receives an unexpected SIGTERM, we need to know:
1. Who sent it (parent PID, process tree, caller stack)
2. What was running (active workers, web server state)
3. What port bindings exist (lsof on the web port)

All capture functions are signal-safe: they avoid allocating memory
where possible and use short subprocess timeouts.
"""

import logging
import os
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---- Constants ----------------------------------------------------------------

DIAGNOSTICS_LOG_DIR = Path("tmp/diagnostics")

# Maximum time (seconds) for subprocess calls inside signal handlers.
# Must be short to avoid blocking the main process.
_SUBPROCESS_TIMEOUT = 3


# ---- Diagnostic capture -------------------------------------------------------


def capture_process_tree() -> str:
    """Capture the process tree around the current PID using ps.

    Returns a multi-line string showing the process hierarchy, or an
    error message if ps is unavailable.
    """
    my_pid = os.getpid()
    my_ppid = os.getppid()
    lines = [f"Current PID: {my_pid}, Parent PID: {my_ppid}"]

    # Get parent process info
    try:
        result = subprocess.run(
            ["ps", "-p", str(my_ppid), "-o", "pid,ppid,pgid,user,command"],
            capture_output=True, text=True, timeout=_SUBPROCESS_TIMEOUT,
        )
        lines.append(f"Parent process:\n{result.stdout.strip()}")
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        lines.append(f"Parent process: <unavailable: {exc}>")

    # Get all pipeline-related processes
    try:
        result = subprocess.run(
            ["ps", "-eo", "pid,ppid,pgid,user,start,command"],
            capture_output=True, text=True, timeout=_SUBPROCESS_TIMEOUT,
        )
        relevant = []
        for line in result.stdout.splitlines():
            lower = line.lower()
            if any(kw in lower for kw in [
                "auto-pipeline", "langgraph_pipeline", "claude",
                str(my_pid), str(my_ppid), "python",
            ]):
                relevant.append(line)
        if relevant:
            header = result.stdout.splitlines()[0] if result.stdout.splitlines() else ""
            lines.append(f"Related processes:\n{header}")
            lines.extend(relevant[:50])  # cap to avoid huge output
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        lines.append(f"Process list: <unavailable: {exc}>")

    return "\n".join(lines)


def capture_port_bindings(port: int) -> str:
    """Capture what processes are bound to the given TCP port.

    Returns a multi-line string from lsof, or an error message.
    """
    try:
        result = subprocess.run(
            ["lsof", "-i", f"tcp:{port}"],
            capture_output=True, text=True, timeout=_SUBPROCESS_TIMEOUT,
        )
        output = result.stdout.strip()
        return output if output else f"No processes bound to port {port}"
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        return f"Port bindings: <unavailable: {exc}>"


def capture_stack_trace() -> str:
    """Capture the current stack trace of all threads.

    Returns a multi-line string showing every thread's call stack.
    """
    import threading
    lines = []
    frames = sys._current_frames()
    for thread_id, frame in frames.items():
        thread_name = "<unknown>"
        for t in threading.enumerate():
            if t.ident == thread_id:
                thread_name = t.name
                break
        lines.append(f"\n--- Thread {thread_id} ({thread_name}) ---")
        lines.extend(traceback.format_stack(frame))
    return "".join(lines)


def capture_full_diagnostic(
    signal_name: str,
    web_port: int = 7070,
    active_worker_pids: Optional[list[int]] = None,
    extra_context: Optional[dict] = None,
) -> str:
    """Capture a complete forensic snapshot and return it as a string.

    Also writes the report to a timestamped file under DIAGNOSTICS_LOG_DIR.

    Args:
        signal_name: The signal that triggered the capture (e.g. "SIGTERM").
        web_port: The web server port to check bindings on.
        active_worker_pids: List of known active worker PIDs (from supervisor).
        extra_context: Arbitrary key-value pairs to include in the report.

    Returns:
        The full diagnostic report as a string.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    my_pid = os.getpid()
    my_ppid = os.getppid()

    sections = [
        f"{'=' * 72}",
        f"SIGNAL DIAGNOSTIC REPORT",
        f"{'=' * 72}",
        f"Signal     : {signal_name}",
        f"Timestamp  : {timestamp}",
        f"PID        : {my_pid}",
        f"Parent PID : {my_ppid}",
        f"Python     : {sys.executable}",
        f"Argv       : {sys.argv}",
        f"CWD        : {os.getcwd()}",
        "",
    ]

    if extra_context:
        sections.append("--- Extra Context ---")
        for k, v in extra_context.items():
            sections.append(f"  {k}: {v}")
        sections.append("")

    if active_worker_pids is not None:
        sections.append(f"--- Active Workers ({len(active_worker_pids)}) ---")
        for wpid in active_worker_pids:
            alive = _is_pid_alive(wpid)
            sections.append(f"  PID {wpid}: {'alive' if alive else 'dead'}")
        sections.append("")

    sections.append("--- Port Bindings (tcp:{}) ---".format(web_port))
    sections.append(capture_port_bindings(web_port))
    sections.append("")

    sections.append("--- Process Tree ---")
    sections.append(capture_process_tree())
    sections.append("")

    sections.append("--- Stack Traces (all threads) ---")
    sections.append(capture_stack_trace())
    sections.append("")

    sections.append(f"{'=' * 72}")
    sections.append("END OF DIAGNOSTIC REPORT")
    sections.append(f"{'=' * 72}")

    report = "\n".join(sections)

    # Write to file
    try:
        DIAGNOSTICS_LOG_DIR.mkdir(parents=True, exist_ok=True)
        filepath = DIAGNOSTICS_LOG_DIR / f"signal-{signal_name.lower()}-{timestamp}.txt"
        filepath.write_text(report)
        logger.warning("Signal diagnostic report written to %s", filepath)
    except OSError as exc:
        logger.error("Failed to write diagnostic report: %s", exc)

    return report


def format_kill_audit(
    caller: str,
    target_pid: int,
    signal_name: str,
    port: int,
    reason: str,
) -> str:
    """Format an audit log entry for an outbound kill() call.

    Called by _kill_process_on_port and _stop_dev_server to record
    every SIGTERM/SIGKILL they send, with full caller context.
    """
    my_pid = os.getpid()
    stack = "".join(traceback.format_stack()[:-1])  # exclude this function
    return (
        f"KILL AUDIT: {caller} sending {signal_name} to PID {target_pid} "
        f"(port {port}, reason: {reason})\n"
        f"  Sender PID: {my_pid}\n"
        f"  Stack:\n{stack}"
    )


def _is_pid_alive(pid: int) -> bool:
    """Check if a PID is alive using signal 0."""
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False
