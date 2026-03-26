#!/usr/bin/env python3
# langgraph_pipeline/supervisor.py
# Supervisor loop: dispatches worker subprocesses for parallel backlog item processing.
# Design: docs/plans/2026-03-24-06-parallel-item-processing-supervisor-worker-model-design.md

"""Supervisor for parallel backlog item processing.

Maintains a pool of worker subprocesses (one per active item). Each iteration
reaps any finished workers, reads their result JSON, updates the cumulative
cost, and dispatches new workers while slots remain open.

The result file for each worker is written to WORKER_RESULT_DIR using a
UUID-based name so the path is known before subprocess.Popen() is called.

Exit codes (matching cli.py constants):
    0 -- clean shutdown (SIGINT/SIGTERM)
    1 -- unhandled error
    2 -- budget exhausted
"""

import json
import logging
import os
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

from langgraph_pipeline.pipeline.nodes.idea_classifier import process_ideas
from langgraph_pipeline.pipeline.nodes.scan import (
    CLAIM_META_SUFFIX,
    claim_item,
    scan_backlog,
    unclaim_item,
)
from langgraph_pipeline.pipeline.state import PipelineState
from langgraph_pipeline.shared.langsmith import read_trace_id_from_file
from langgraph_pipeline.shared.paths import BACKLOG_DIRS, CLAIMED_DIR, PLANS_DIR, WORKER_RESULT_DIR
from langgraph_pipeline.slack.notifier import SlackNotifier
from langgraph_pipeline.web.dashboard_state import get_dashboard_state
from langgraph_pipeline.web.proxy import get_proxy

# ─── Constants ────────────────────────────────────────────────────────────────

EXIT_CODE_CLEAN = 0
EXIT_CODE_ERROR = 1
EXIT_CODE_BUDGET_EXHAUSTED = 2

# How long to sleep when the backlog is empty and no workers are active.
SCAN_SLEEP_SECONDS = 15

# How long to sleep between worker-poll iterations when workers are active.
WORKER_POLL_SLEEP_SECONDS = 2

# Result file name template; uses a UUID generated before spawning.
_RESULT_FILE_TEMPLATE = "worker-{uid}.result.json"

# ─── Types ────────────────────────────────────────────────────────────────────

# Active worker record stored per PID.
# Fields: (claimed_path, result_file_path, item_type, start_time_monotonic)
WorkerRecord = tuple[str, str, str, float]

# ─── Logging ──────────────────────────────────────────────────────────────────

logger = logging.getLogger(__name__)


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_result_file_path() -> str:
    """Generate a unique result file path for a worker subprocess.

    Uses a UUID so the path is known before Popen() is called (the PID is
    only available after the process starts).
    """
    uid = uuid.uuid4().hex[:12]
    return os.path.join(WORKER_RESULT_DIR, _RESULT_FILE_TEMPLATE.format(uid=uid))


def _unclaim_orphaned_items() -> None:
    """Return any items in CLAIMED_DIR to their backlog on supervisor startup.

    When the supervisor restarts after a crash or restart, items that were
    claimed by now-dead workers remain in CLAIMED_DIR. Without cleanup, those
    items are invisible to scan_backlog (which only scans the backlog dirs) and
    are never processed again.

    This function is called once at supervisor startup, before the dispatch
    loop begins. It moves every .md file in CLAIMED_DIR back to its original
    backlog directory based on the item type inferred from the filename context.
    We use the same type-inference logic as _item_type_from_path: default to
    "feature" for ambiguous items, since the worst case is the item re-enters
    the backlog and gets reclassified on the next scan.
    """
    claimed_dir = Path(CLAIMED_DIR)
    if not claimed_dir.exists():
        return

    orphans = list(claimed_dir.glob("*.md"))
    if not orphans:
        return

    logger.warning(
        "Startup: found %d orphaned item(s) in %s — returning to backlog.",
        len(orphans),
        CLAIMED_DIR,
    )
    for md_file in orphans:
        sidecar_path = md_file.parent / (md_file.name + CLAIM_META_SUFFIX)
        if sidecar_path.exists():
            try:
                with open(sidecar_path, "r") as f:
                    meta = json.load(f)
                item_type = meta.get("item_type", "feature")
                sidecar_path.unlink()
            except (OSError, json.JSONDecodeError):
                item_type = "feature"
        else:
            # Fall back to slug-heuristic when no sidecar is present.
            path_str = str(md_file).lower()
            if "defect" in path_str:
                item_type = "defect"
            elif "analysis" in path_str:
                item_type = "analysis"
            else:
                item_type = "feature"
        try:
            unclaim_item(str(md_file), item_type)
            logger.info("Returned orphan %s to %s backlog.", md_file.name, item_type)
        except (OSError, KeyError) as exc:
            logger.warning("Could not return orphan %s: %s", md_file.name, exc)

    # Remove any leftover sidecar files whose .md has already been archived.
    for sidecar in claimed_dir.glob("*" + CLAIM_META_SUFFIX):
        if not sidecar.exists():
            continue
        md_path = sidecar.parent / sidecar.name[: -len(CLAIM_META_SUFFIX)]
        if not md_path.exists():
            sidecar.unlink()
            logger.info("Removed stale claim sidecar %s", sidecar.name)


def _cleanup_orphaned_plan_yamls() -> None:
    """Delete plan YAML files in PLANS_DIR that have no corresponding active item.

    A plan YAML is considered orphaned when the item it was created for no longer
    exists in any backlog directory or in CLAIMED_DIR. This happens when the
    pipeline is killed between plan creation and archival. Without this cleanup,
    stale YAMLs accumulate indefinitely across restarts.

    Called once at startup, after _unclaim_orphaned_items() so that any claimed
    items returned to the backlog are visible before we evaluate active slugs.
    """
    plans_dir = Path(PLANS_DIR)
    if not plans_dir.exists():
        return

    yaml_files = list(plans_dir.glob("*.yaml"))
    if not yaml_files:
        return

    # Build the set of active slugs (claimed + all backlog dirs).
    active_slugs: set[str] = set()
    claimed_dir = Path(CLAIMED_DIR)
    if claimed_dir.exists():
        for md in claimed_dir.glob("*.md"):
            active_slugs.add(md.stem)
    for backlog_path in BACKLOG_DIRS.values():
        backlog_dir = Path(backlog_path)
        if backlog_dir.exists():
            for md in backlog_dir.glob("*.md"):
                active_slugs.add(md.stem)

    removed = 0
    for yaml_file in yaml_files:
        if yaml_file.stem not in active_slugs:
            try:
                yaml_file.unlink()
                removed += 1
            except OSError as exc:
                logger.warning("Could not remove stale plan YAML %s: %s", yaml_file.name, exc)

    if removed:
        logger.info("Startup: removed %d orphaned plan YAML(s) from %s.", removed, PLANS_DIR)


def _build_scan_state() -> PipelineState:
    """Build a minimal PipelineState that triggers a fresh backlog scan."""
    state: PipelineState = {
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
        "quota_exhausted": False,
        "budget_cap_usd": None,
        "session_cost_usd": 0.0,
        "session_input_tokens": 0,
        "session_output_tokens": 0,
        "intake_count_defects": 0,
        "intake_count_features": 0,
    }
    return state


def _scan_next_item() -> Optional[tuple[str, str, str]]:
    """Scan the backlog and return (item_path, item_slug, item_type) or None.

    Calls scan_backlog() directly (no graph, no tracing) to find the next
    candidate item. Returns None when the backlog is empty.
    """
    scan_state = _build_scan_state()
    result = scan_backlog(scan_state)
    item_path: str = result.get("item_path", "")
    if not item_path:
        return None
    return (
        item_path,
        result.get("item_slug", ""),
        result.get("item_type", "feature"),
    )


def _read_result_file(result_file: str) -> Optional[dict]:
    """Read and parse the worker result JSON. Returns None on any error."""
    try:
        with open(result_file, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _remove_result_file(result_file: str) -> None:
    """Remove the worker result file (best-effort, ignores missing files)."""
    try:
        os.remove(result_file)
    except FileNotFoundError:
        pass
    except OSError as exc:
        logger.warning("Could not remove result file %s: %s", result_file, exc)


def _spawn_worker(claimed_path: str, result_file: str, item_type: str, item_slug: str) -> subprocess.Popen:
    """Spawn a worker subprocess for the given claimed item.

    Runs `python -m langgraph_pipeline.worker` with --item-path,
    --result-file, --item-type, and --item-slug. The slug and type are
    forwarded explicitly because the claimed path no longer contains the
    original backlog directory name needed to derive them.
    Returns the Popen object (PID available via .pid).
    """
    cmd = [
        sys.executable,
        "-m",
        "langgraph_pipeline.worker",
        "--item-path",
        claimed_path,
        "--result-file",
        result_file,
        "--item-type",
        item_type,
        "--item-slug",
        item_slug,
    ]
    logger.info("Spawning worker: item=%s result=%s", claimed_path, result_file)
    return subprocess.Popen(cmd)


# ─── Worker reaping ───────────────────────────────────────────────────────────


def _reap_one_worker(
    pid: int,
    record: WorkerRecord,
    cumulative_cost_usd: list[float],
    budget_cap_usd: Optional[float],
    slack: Optional[SlackNotifier],
) -> bool:
    """Process the result of a single finished worker.

    Reads the result file, updates cumulative cost, and unclams the item on
    failure. Removes the result file after reading.

    Args:
        pid: PID of the finished worker.
        record: WorkerRecord for this worker.
        cumulative_cost_usd: Single-element list holding the running cost total.
        budget_cap_usd: Budget cap in USD, or None.
        slack: SlackNotifier, or None.

    Returns:
        True if the budget cap was reached after adding this worker's cost.
    """
    claimed_path, result_file, item_type, start_time = record
    duration_s = time.monotonic() - start_time

    result = _read_result_file(result_file)
    _remove_result_file(result_file)

    run_id = read_trace_id_from_file(claimed_path)

    if result is None:
        # Worker crashed without writing a result file — return item to backlog.
        crash_msg = (
            f"Worker PID {pid}: crash detected (no result file). "
            f"Item: {claimed_path} duration={duration_s:.1f}s"
        )
        logger.error(crash_msg)
        get_dashboard_state().add_error(crash_msg)
        get_dashboard_state().remove_active_worker(pid, "fail", 0.0, duration_s)
        proxy = get_proxy()
        if proxy is not None:
            proxy.record_completion(Path(claimed_path).stem, item_type, "fail", 0.0, duration_s, run_id=run_id)
        try:
            unclaim_item(claimed_path, item_type)
            logger.info("Unclaimed %s back to %s backlog.", claimed_path, item_type)
        except Exception as exc:
            logger.error(
                "Failed to unclaim %s after worker crash: %s", claimed_path, exc
            )
        return False

    cost_usd: float = result.get("cost_usd", 0.0)
    success: bool = result.get("success", False)
    message: str = result.get("message", "")
    item_path: str = result.get("item_path", claimed_path)

    cumulative_cost_usd[0] += cost_usd

    if success:
        logger.info(
            "Worker PID %d: success. item=%s cost=~$%.4f duration=%.1fs",
            pid,
            item_path,
            cost_usd,
            duration_s,
        )
        get_dashboard_state().remove_active_worker(pid, "success", cost_usd, duration_s)
        proxy = get_proxy()
        if proxy is not None:
            proxy.record_completion(Path(claimed_path).stem, item_type, "success", cost_usd, duration_s, run_id=run_id)
    else:
        # Handled failure (e.g. quota exhausted) — return item to backlog for retry.
        failure_msg = (
            f"Worker PID {pid}: handled failure. item={item_path} "
            f"cost=~${cost_usd:.4f} duration={duration_s:.1f}s message={message}"
        )
        logger.warning(failure_msg)
        get_dashboard_state().add_error(failure_msg)
        get_dashboard_state().remove_active_worker(pid, "warn", cost_usd, duration_s)
        proxy = get_proxy()
        if proxy is not None:
            proxy.record_completion(Path(claimed_path).stem, item_type, "warn", cost_usd, duration_s, run_id=run_id)
        try:
            unclaim_item(claimed_path, item_type)
            logger.info("Unclaimed %s back to %s backlog.", claimed_path, item_type)
        except Exception as exc:
            logger.error(
                "Failed to unclaim %s after worker failure: %s", claimed_path, exc
            )

    if budget_cap_usd is not None and cumulative_cost_usd[0] >= budget_cap_usd:
        logger.warning(
            "Budget cap reached: cumulative=~$%.4f >= cap=~$%.2f",
            cumulative_cost_usd[0],
            budget_cap_usd,
        )
        if slack is not None:
            slack.send_status(
                f"Budget cap ~${budget_cap_usd:.2f} USD reached "
                f"(spent ~${cumulative_cost_usd[0]:.4f}). "
                "Stopping dispatch of new items.",
                level="warning",
            )
        return True

    return False


def _reap_finished_workers(
    active_workers: dict[int, WorkerRecord],
    cumulative_cost_usd: list[float],
    budget_cap_usd: Optional[float],
    slack: Optional[SlackNotifier],
) -> bool:
    """Non-blocking reap of all finished workers using WNOHANG.

    Iterates over a snapshot of active_workers pids, calls os.waitpid with
    WNOHANG for each, and removes finished workers from the dict.

    Returns:
        True if the budget cap was reached during this reap pass.
    """
    budget_exceeded = False

    for pid in list(active_workers.keys()):
        try:
            reaped_pid, _status = os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            logger.warning("Worker PID %d already reaped; removing from tracking.", pid)
            record = active_workers.pop(pid, None)
            if record is not None:
                elapsed_s = time.monotonic() - record[3]
                get_dashboard_state().remove_active_worker(pid, "fail", 0.0, elapsed_s)
            continue

        if reaped_pid == 0:
            # Worker still running.
            continue

        record = active_workers.pop(pid)
        if _reap_one_worker(pid, record, cumulative_cost_usd, budget_cap_usd, slack):
            budget_exceeded = True

    return budget_exceeded


# ─── Dispatch ─────────────────────────────────────────────────────────────────


def _try_dispatch_one(active_workers: dict[int, WorkerRecord]) -> bool:
    """Scan for a work item, claim it, and spawn a worker.

    Args:
        active_workers: Mutable dict updated with the new worker on success.

    Returns:
        True if a worker was dispatched, False if no item was available or
        the claim race was lost.
    """
    candidate = _scan_next_item()
    if candidate is None:
        return False

    item_path, item_slug, item_type = candidate

    claimed = claim_item(item_path, item_type)
    if not claimed:
        logger.debug("Lost claim race on %s — another process claimed it.", item_path)
        return False

    claimed_path = os.path.join(CLAIMED_DIR, os.path.basename(item_path))
    result_file = _make_result_file_path()

    try:
        proc = _spawn_worker(claimed_path, result_file, item_type, item_slug)
        pid = proc.pid
        start_time = time.monotonic()
        active_workers[pid] = (claimed_path, result_file, item_type, start_time)
        run_id = read_trace_id_from_file(claimed_path)
        get_dashboard_state().add_active_worker(pid, item_slug, item_type, start_time, run_id=run_id)
        logger.info(
            "Dispatched worker PID %d for %s (type=%s)", pid, claimed_path, item_type
        )
        return True

    except Exception as exc:
        logger.error("Failed to spawn worker for %s: %s", claimed_path, exc)
        try:
            unclaim_item(claimed_path, item_type)
        except Exception as unclaim_exc:
            logger.error(
                "Failed to unclaim %s after spawn error: %s", claimed_path, unclaim_exc
            )
        return False


# ─── Main supervisor loop ─────────────────────────────────────────────────────


def run_supervisor_loop(
    max_workers: int,
    budget_cap_usd: Optional[float],
    dry_run: bool,
    shutdown_event: threading.Event,
    slack: Optional[SlackNotifier],
) -> int:
    """Run the supervisor dispatch loop until shutdown or budget exhaustion.

    Maintains a pool of worker subprocesses (at most max_workers active at
    once). Each iteration:
    1. Reaps finished workers (non-blocking, WNOHANG), reads results, updates cost.
    2. Dispatches new workers while slots are open and budget is not exceeded.
    3. Sleeps SCAN_SLEEP_SECONDS when no workers are active (backlog empty),
       or WORKER_POLL_SLEEP_SECONDS when workers are active.

    Args:
        max_workers: Maximum number of concurrent worker subprocesses.
        budget_cap_usd: Stop dispatching new items when cumulative cost reaches
            this amount (USD). None means no cap.
        dry_run: When True, log what would be done without spawning workers.
        shutdown_event: Set by signal handlers to request graceful shutdown.
        slack: SlackNotifier instance, or None if Slack is disabled.

    Returns:
        EXIT_CODE_CLEAN, EXIT_CODE_BUDGET_EXHAUSTED, or EXIT_CODE_ERROR.
    """
    if dry_run:
        logger.info(
            "[DRY RUN] Supervisor loop: max_workers=%d budget_cap=%s",
            max_workers,
            f"~${budget_cap_usd:.2f}" if budget_cap_usd is not None else "none",
        )
        while not shutdown_event.is_set():
            logger.info("[DRY RUN] Would dispatch up to %d workers.", max_workers)
            shutdown_event.wait(SCAN_SLEEP_SECONDS)
        logger.info("Shutdown event set — exiting dry-run supervisor loop.")
        return EXIT_CODE_CLEAN

    active_workers: dict[int, WorkerRecord] = {}
    cumulative_cost_usd: list[float] = [0.0]
    budget_exceeded = False

    # Cleanup: return any items orphaned in CLAIMED_DIR by a previous run,
    # then delete any plan YAMLs that have no corresponding active item.
    _unclaim_orphaned_items()
    _cleanup_orphaned_plan_yamls()

    logger.info(
        "Supervisor starting: max_workers=%d budget_cap=%s",
        max_workers,
        f"~${budget_cap_usd:.2f} USD" if budget_cap_usd is not None else "none",
    )

    try:
        while not shutdown_event.is_set():
            ideas_processed = process_ideas(dry_run)
            if ideas_processed > 0:
                logger.info("Ideas intake: processed %d idea(s)", ideas_processed)
            # Step 1: Reap any finished workers (non-blocking).
            if active_workers:
                budget_exceeded = _reap_finished_workers(
                    active_workers, cumulative_cost_usd, budget_cap_usd, slack
                )

            # Step 2: Dispatch new workers while slots are available.
            if not budget_exceeded and not shutdown_event.is_set():
                while len(active_workers) < max_workers and not shutdown_event.is_set():
                    dispatched = _try_dispatch_one(active_workers)
                    if not dispatched:
                        break  # Backlog empty or claim lost; don't spin.

            # Step 3: Sleep strategy depends on whether workers are active.
            if not active_workers:
                logger.debug(
                    "No active workers and backlog empty. Sleeping %ds.",
                    SCAN_SLEEP_SECONDS,
                )
                shutdown_event.wait(SCAN_SLEEP_SECONDS)
            else:
                shutdown_event.wait(WORKER_POLL_SLEEP_SECONDS)

        # Graceful shutdown: wait for in-flight workers to complete.
        if active_workers:
            logger.info(
                "Shutdown requested; waiting for %d active worker(s) to finish.",
                len(active_workers),
            )
            for pid in list(active_workers.keys()):
                try:
                    os.waitpid(pid, 0)
                except ChildProcessError:
                    pass

            # Final reap to record costs and handle any failures.
            _reap_finished_workers(
                active_workers, cumulative_cost_usd, budget_cap_usd, slack
            )

        logger.info(
            "Supervisor exiting. Total cumulative cost: ~$%.4f USD.",
            cumulative_cost_usd[0],
        )

        if budget_exceeded:
            return EXIT_CODE_BUDGET_EXHAUSTED
        return EXIT_CODE_CLEAN

    except Exception as exc:
        logger.exception("Unhandled error in supervisor loop: %s", exc)
        return EXIT_CODE_ERROR
