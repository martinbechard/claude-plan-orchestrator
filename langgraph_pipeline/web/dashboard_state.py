# langgraph_pipeline/web/dashboard_state.py
# Thread-safe DashboardState singleton for the pipeline activity dashboard.
# Design: docs/plans/2026-03-26-03-dashboard-items-stuck-running-design.md
# Design: docs/plans/2026-03-26-10-error-stream-always-empty-design.md

"""Thread-safe state container for the pipeline activity dashboard.

Holds active worker info, recent completions, session cost, and error stream.
A module-level singleton is shared between the supervisor thread (writer) and
the SSE endpoint in the uvicorn async loop (reader).
"""

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from langgraph_pipeline.shared.paths import BACKLOG_DIRS
from langgraph_pipeline.web.proxy import get_proxy

# ─── Constants ────────────────────────────────────────────────────────────────

MAX_RECENT_COMPLETIONS = 20
MAX_RECENT_ERRORS = 50

# ─── Data Shapes ──────────────────────────────────────────────────────────────


@dataclass
class WorkerInfo:
    """Snapshot of a single active worker process."""

    pid: int
    slug: str
    item_type: str  # "defect" | "feature" | "analysis"
    start_time: float  # time.monotonic()
    estimated_cost_usd: float = 0.0
    run_id: Optional[str] = None
    tokens_in: int = 0
    tokens_out: int = 0
    token_history: list[tuple[float, int]] = field(default_factory=list)

    def record_token_sample(self) -> None:
        """Append the current total token count with a monotonic timestamp."""
        self.token_history.append((time.monotonic(), self.tokens_in + self.tokens_out))

    def current_velocity(self) -> float:
        """Compute tokens/min from the last two samples. Returns 0.0 if < 2 samples."""
        if len(self.token_history) < 2:
            return 0.0
        t1, tok1 = self.token_history[-2]
        t2, tok2 = self.token_history[-1]
        dt = t2 - t1
        if dt <= 0:
            return 0.0
        return (tok2 - tok1) / (dt / 60.0)

    def get_velocity_series(self) -> list[tuple[float, float]]:
        """Convert token_history into (elapsed_s, tokens_per_min) pairs."""
        series: list[tuple[float, float]] = []
        for i in range(1, len(self.token_history)):
            t_prev, tok_prev = self.token_history[i - 1]
            t_curr, tok_curr = self.token_history[i]
            dt = t_curr - t_prev
            if dt <= 0:
                continue
            velocity = (tok_curr - tok_prev) / (dt / 60.0)
            elapsed_s = t_curr - self.start_time
            series.append((elapsed_s, velocity))
        return series


@dataclass
class CompletionRecord:
    """Record of a completed work item."""

    slug: str
    item_type: str
    outcome: str  # "success" | "warn" | "fail"
    cost_usd: float
    duration_s: float
    finished_at: float  # time.time() for display
    run_id: Optional[str] = None


# ─── DashboardState ───────────────────────────────────────────────────────────


class DashboardState:
    """Thread-safe container for all pipeline dashboard metrics.

    The supervisor loop acquires the internal lock to mutate state; the SSE
    endpoint acquires the same lock (briefly) to read a serialisable snapshot.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.active_workers: dict[int, WorkerInfo] = {}
        self.recent_completions: list[CompletionRecord] = []
        self.session_cost_usd: float = 0.0
        self.session_start: float = time.monotonic()
        self.recent_errors: list[str] = []
        self._total_processed: int = 0

    # ─── Mutators ─────────────────────────────────────────────────────────────

    def add_active_worker(
        self,
        pid: int,
        slug: str,
        item_type: str,
        start_time: float,
        estimated_cost_usd: float = 0.0,
        run_id: Optional[str] = None,
    ) -> None:
        """Register a newly dispatched worker.

        Args:
            pid: Process ID of the worker.
            slug: Work item slug.
            item_type: One of "defect", "feature", or "analysis".
            start_time: Monotonic timestamp at dispatch (time.monotonic()).
            estimated_cost_usd: Optional pre-run cost estimate.
            run_id: LangSmith trace UUID, if available at dispatch time.
        """
        with self._lock:
            self.active_workers[pid] = WorkerInfo(
                pid=pid,
                slug=slug,
                item_type=item_type,
                start_time=start_time,
                estimated_cost_usd=estimated_cost_usd,
                run_id=run_id,
            )

    def remove_active_worker(
        self,
        pid: int,
        outcome: str,
        cost_usd: float,
        duration_s: float,
    ) -> None:
        """Reap a finished worker and record its completion.

        If the PID is not found in active_workers the call is a no-op, which
        keeps error paths safe to call without a prior add.

        Args:
            pid: Process ID of the worker to remove.
            outcome: One of "success", "warn", or "fail".
            cost_usd: Actual API cost incurred.
            duration_s: Wall-clock seconds the worker ran.
        """
        with self._lock:
            worker = self.active_workers.pop(pid, None)
            if worker is None:
                return

            record = CompletionRecord(
                slug=worker.slug,
                item_type=worker.item_type,
                outcome=outcome,
                cost_usd=cost_usd,
                duration_s=duration_s,
                finished_at=time.time(),
                run_id=worker.run_id,
            )
            self.recent_completions.insert(0, record)
            if len(self.recent_completions) > MAX_RECENT_COMPLETIONS:
                self.recent_completions = self.recent_completions[:MAX_RECENT_COMPLETIONS]

            self.session_cost_usd += cost_usd
            self._total_processed += 1

    def update_worker_tokens(self, pid: int, tokens_in: int, tokens_out: int) -> None:
        """Update the token counts for an active worker.

        Called by the supervisor polling loop after querying token counts from
        the traces DB for the worker's current run_id.

        Args:
            pid: Process ID of the worker to update.
            tokens_in: Total input tokens consumed so far in this run.
            tokens_out: Total output tokens produced so far in this run.
        """
        with self._lock:
            worker = self.active_workers.get(pid)
            if worker is not None:
                worker.tokens_in = tokens_in
                worker.tokens_out = tokens_out

    def update_worker_run_id(self, pid: int, run_id: str) -> None:
        """Update the LangSmith run_id for an active worker once it becomes available.

        Called by the supervisor polling loop when it detects that a worker
        previously registered with run_id=None has since written its trace ID
        to the item file.

        Args:
            pid: Process ID of the worker to update.
            run_id: LangSmith trace UUID now available for this worker.
        """
        with self._lock:
            worker = self.active_workers.get(pid)
            if worker is not None:
                worker.run_id = run_id

    def add_error(self, message: str) -> None:
        """Prepend an error message to the recent-errors stream.

        Args:
            message: Human-readable error description.
        """
        with self._lock:
            self.recent_errors.insert(0, message)
            if len(self.recent_errors) > MAX_RECENT_ERRORS:
                self.recent_errors = self.recent_errors[:MAX_RECENT_ERRORS]

    def sweep_dead_workers(self) -> None:
        """Remove workers whose OS processes are no longer alive.

        Uses os.kill(pid, 0) to probe each active worker. If the process is
        gone (OSError with errno ESRCH), the worker is reaped as a failure
        with zero cost and an elapsed time computed from its stored start_time.

        Called at the top of snapshot() so the dashboard never shows zombie
        entries for workers that died without going through the normal reap path.
        Must NOT be called while self._lock is held (remove_active_worker
        acquires the lock internally).
        """
        with self._lock:
            pids = list(self.active_workers.keys())
        for pid in pids:
            try:
                os.kill(pid, 0)
            except OSError:
                with self._lock:
                    worker = self.active_workers.get(pid)
                if worker is None:
                    continue
                elapsed_s = time.monotonic() - worker.start_time
                self.remove_active_worker(pid, "fail", 0.0, elapsed_s)

    # ─── Snapshot ─────────────────────────────────────────────────────────────

    def snapshot(self) -> dict:
        """Return a serialisable dict representing the current dashboard state.

        Computes queue_count by globbing *.md files across all BACKLOG_DIRS.
        All fields are primitive types safe for JSON serialisation.

        Returns:
            Dict with keys: active_workers, recent_completions, queue_count,
            session_cost_usd, session_elapsed_s, active_count, total_processed,
            recent_errors.
        """
        self.sweep_dead_workers()
        now = time.monotonic()
        with self._lock:
            active_list = []
            for w in self.active_workers.values():
                elapsed_s = now - w.start_time
                tokens_per_minute = w.current_velocity()
                velocity_history = [
                    {"elapsed_s": round(es, 1), "tokens_per_minute": round(v, 1)}
                    for es, v in w.get_velocity_series()
                ]
                active_list.append(
                    {
                        "pid": w.pid,
                        "slug": w.slug,
                        "item_type": w.item_type,
                        "elapsed_s": elapsed_s,
                        "estimated_cost_usd": w.estimated_cost_usd,
                        "run_id": w.run_id,
                        "tokens_in": w.tokens_in,
                        "tokens_out": w.tokens_out,
                        "tokens_per_minute": tokens_per_minute,
                        "velocity_history": velocity_history,
                    }
                )
            proxy = get_proxy()
            if proxy is not None:
                completions_list = proxy.list_completions()
            else:
                completions_list = [
                    {
                        "slug": c.slug,
                        "item_type": c.item_type,
                        "outcome": c.outcome,
                        "cost_usd": c.cost_usd,
                        "duration_s": c.duration_s,
                        "finished_at": c.finished_at,
                        "run_id": c.run_id,
                    }
                    for c in self.recent_completions
                ]
            errors_copy = list(self.recent_errors)
            session_cost = self.session_cost_usd
            elapsed = time.monotonic() - self.session_start
            active_count = len(self.active_workers)
            total = self._total_processed

        queue_count = _count_queued_items()

        return {
            "active_workers": active_list,
            "recent_completions": completions_list,
            "queue_count": queue_count,
            "session_cost_usd": session_cost,
            "session_elapsed_s": elapsed,
            "active_count": active_count,
            "total_processed": total,
            "recent_errors": errors_copy,
        }


# ─── Queue Helpers ────────────────────────────────────────────────────────────


def _count_queued_items() -> int:
    """Count pending *.md work items across all BACKLOG_DIRS.

    Reads directly from the filesystem — no scan graph — so the web layer
    stays decoupled from the pipeline internals.
    """
    total = 0
    for backlog_path in BACKLOG_DIRS.values():
        directory = Path(backlog_path)
        if directory.is_dir():
            total += len(list(directory.glob("*.md")))
    return total


# ─── Module-Level Singleton ───────────────────────────────────────────────────

_state: Optional[DashboardState] = None
_state_lock = threading.Lock()


def get_dashboard_state() -> DashboardState:
    """Return the module-level DashboardState singleton, creating it if needed."""
    global _state
    if _state is None:
        with _state_lock:
            if _state is None:
                _state = DashboardState()
    return _state


def reset_dashboard_state() -> None:
    """Replace the singleton with a fresh DashboardState instance.

    Intended for use in tests only. Not safe to call while the supervisor
    or SSE endpoint is actively using the state.
    """
    global _state
    with _state_lock:
        _state = DashboardState()


# ─── Logging Handler ──────────────────────────────────────────────────────────


class DashboardErrorHandler(logging.Handler):
    """Logging handler that forwards WARNING+ records to the dashboard error stream.

    Install on the 'langgraph_pipeline' logger (not root) to capture pipeline-internal
    warnings without forwarding noise from third-party libraries.
    """

    def emit(self, record: logging.LogRecord) -> None:
        """Format the record and append it to DashboardState.recent_errors."""
        try:
            msg = f"[{record.levelname}] {record.name}: {self.format(record)}"
            get_dashboard_state().add_error(msg)
        except Exception:
            self.handleError(record)
