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

import yaml

from langgraph_pipeline.pipeline.nodes.idea_classifier import process_ideas
from langgraph_pipeline.pipeline.nodes.scan import (
    CLAIM_META_SUFFIX,
    claim_item,
    scan_backlog,
    unclaim_item,
)
from langgraph_pipeline.pipeline.state import PipelineState
from langgraph_pipeline.shared.hot_reload import CodeChangeMonitor, _perform_restart
from langgraph_pipeline.shared.langsmith import read_trace_id_from_file
from langgraph_pipeline.shared.paths import BACKLOG_DIRS, CLAIMED_DIR, PLANS_DIR, WORKER_OUTPUT_DIR, WORKER_RESULT_DIR
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
WORKER_POLL_SLEEP_SECONDS = 5

# Maximum warn (handled-failure) completions per item before the item is
# archived as exhausted instead of being unclaimed back to the backlog.
MAX_WARN_RETRIES_PER_ITEM = 5

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


def _save_worker_pid_to_sidecar(claimed_path: str, pid: int) -> None:
    """Write the worker PID into the claim sidecar so it can be recovered on crash.

    The claim sidecar already contains item_type. This adds worker_pid so that
    _unclaim_orphaned_items() can transfer it to the plan YAML meta, allowing
    a new worker to reuse the checkpoint DB and thread ID.
    """
    basename = os.path.basename(claimed_path)
    sidecar_path = os.path.join(os.path.dirname(claimed_path), basename + CLAIM_META_SUFFIX)
    try:
        with open(sidecar_path, "r") as f:
            meta = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        meta = {}
    meta["worker_pid"] = pid
    try:
        with open(sidecar_path, "w") as f:
            json.dump(meta, f)
    except OSError as exc:
        logger.warning("Could not save worker PID to sidecar %s: %s", sidecar_path, exc)


def _save_worker_pid_to_plan(slug: str, worker_pid: int) -> None:
    """Write worker_pid into the plan YAML meta so a resume worker can reuse it."""
    plan_path = Path(PLANS_DIR) / f"{slug}.yaml"
    if not plan_path.exists():
        return
    try:
        with open(plan_path, "r") as f:
            plan = yaml.safe_load(f)
        if not plan or "meta" not in plan:
            return
        plan["meta"]["worker_pid"] = worker_pid
        with open(plan_path, "w") as f:
            yaml.dump(plan, f, default_flow_style=False, sort_keys=False)
        logger.info("Saved worker_pid=%d to plan %s for crash recovery.", worker_pid, plan_path)
    except (OSError, yaml.YAMLError) as exc:
        logger.warning("Could not save worker_pid to plan %s: %s", plan_path, exc)


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
        worker_pid = None
        if sidecar_path.exists():
            try:
                with open(sidecar_path, "r") as f:
                    meta = json.load(f)
                source_item = meta.get("source_item", "")
                item_type = meta.get("item_type") or (
                    "defect" if "defect" in source_item.lower()
                    else "investigation" if "investigation" in source_item.lower()
                    else "analysis" if "analysis" in source_item.lower()
                    else "feature"
                )
                worker_pid = meta.get("worker_pid")
                sidecar_path.unlink()
            except (OSError, json.JSONDecodeError):
                # Sidecar unreadable — fall through to slug-heuristic below
                sidecar_path = None  # prevent re-read attempts
                path_str = str(md_file).lower()
                if "defect" in path_str:
                    item_type = "defect"
                elif "investigation" in path_str:
                    item_type = "investigation"
                elif "analysis" in path_str:
                    item_type = "analysis"
                else:
                    item_type = "feature"
        else:
            # Fall back to slug-heuristic when no sidecar is present.
            path_str = str(md_file).lower()
            if "defect" in path_str:
                item_type = "defect"
            elif "investigation" in path_str:
                item_type = "investigation"
            elif "analysis" in path_str:
                item_type = "analysis"
            else:
                item_type = "feature"

        # Transfer worker_pid to plan YAML so a resume worker can reuse the
        # checkpoint DB and thread ID from the crashed worker.
        if worker_pid:
            _save_worker_pid_to_plan(md_file.stem, worker_pid)

        try:
            unclaim_item(str(md_file), item_type)
            logger.info("Returned orphan %s to %s backlog (worker_pid=%s).", md_file.name, item_type, worker_pid)
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
            # Preserve plan to permanent location before deletion
            try:
                import shutil
                output_dir = Path(WORKER_OUTPUT_DIR) / yaml_file.stem
                output_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(yaml_file), output_dir / "plan.yaml")
            except OSError:
                pass
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


def _scan_next_item() -> Optional[tuple[str, str, str, Optional[str], Optional[int]]]:
    """Scan the backlog and return (item_path, item_slug, item_type, plan_path, worker_pid) or None.

    Calls scan_backlog() directly (no graph, no tracing) to find the next
    candidate item. Returns None when the backlog is empty. plan_path and
    worker_pid are set when an in-progress plan exists for the item (crash
    recovery), allowing the new worker to reuse the previous checkpoint.
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
        result.get("plan_path"),
        result.get("worker_pid"),
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


def _spawn_worker(
    claimed_path: str,
    result_file: str,
    item_type: str,
    item_slug: str,
    plan_path: Optional[str] = None,
    resume_pid: Optional[int] = None,
) -> subprocess.Popen:
    """Spawn a worker subprocess for the given claimed item.

    Runs `python -m langgraph_pipeline.worker` with --item-path,
    --result-file, --item-type, and --item-slug. The slug and type are
    forwarded explicitly because the claimed path no longer contains the
    original backlog directory name needed to derive them. When resume_pid
    is set (crash recovery), the worker reuses the crashed worker's
    checkpoint DB and thread ID to resume from the last completed node.
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
    if resume_pid is not None:
        cmd.extend(["--resume-pid", str(resume_pid)])
    logger.info("Spawning worker: item=%s result=%s resume_pid=%s", claimed_path, result_file, resume_pid)
    return subprocess.Popen(cmd)


# ─── Worker reaping ───────────────────────────────────────────────────────────


def _compute_final_velocity(pid: int, duration_s: float) -> float:
    """Compute tokens-per-minute for a worker about to be reaped.

    Reads the worker's accumulated token counts from DashboardState (which has
    been kept current by _refresh_worker_token_counts). Returns 0.0 when the
    worker is not found or has no token data.

    Args:
        pid: Process ID of the worker.
        duration_s: Wall-clock seconds the worker ran.

    Returns:
        Tokens per minute as a float (0.0 if no token data is available).
    """
    dashboard = get_dashboard_state()
    with dashboard._lock:
        worker = dashboard.active_workers.get(pid)
        if worker is None or (worker.tokens_in == 0 and worker.tokens_out == 0):
            return 0.0
        total_tokens = worker.tokens_in + worker.tokens_out

    elapsed_min = max(duration_s / 60.0, 0.001)
    return total_tokens / elapsed_min


def _reap_one_worker(
    pid: int,
    record: WorkerRecord,
    cumulative_cost_usd: list[float],
    budget_cap_usd: Optional[float],
    slack: Optional[SlackNotifier],
    warn_counts: Optional[dict[str, int]] = None,
) -> bool:
    """Process the result of a single finished worker.

    Reads the result file, updates cumulative cost, and unclaims the item on
    failure. When an item exceeds MAX_WARN_RETRIES_PER_ITEM consecutive warns,
    it is archived as exhausted instead of being returned to the backlog.

    Args:
        pid: PID of the finished worker.
        record: WorkerRecord for this worker.
        cumulative_cost_usd: Single-element list holding the running cost total.
        budget_cap_usd: Budget cap in USD, or None.
        slack: SlackNotifier, or None.
        warn_counts: Mutable dict tracking warn completions per item slug.

    Returns:
        True if the budget cap was reached after adding this worker's cost.
    """
    claimed_path, result_file, item_type, start_time = record
    duration_s = time.monotonic() - start_time

    result = _read_result_file(result_file)
    _remove_result_file(result_file)

    run_id = read_trace_id_from_file(claimed_path)

    # Compute final velocity from accumulated token counts before removing the worker.
    final_velocity = _compute_final_velocity(pid, duration_s)

    if result is None:
        # Worker crashed without writing a result file — return item to backlog.
        crash_msg = (
            f"Worker PID {pid}: crash detected (no result file). "
            f"Item: {claimed_path} duration={duration_s:.1f}s"
        )
        logger.error(crash_msg)
        get_dashboard_state().add_notification(crash_msg)
        get_dashboard_state().remove_active_worker(pid, "fail", 0.0, duration_s)
        proxy = get_proxy()
        if proxy is not None:
            proxy.record_completion(
                Path(claimed_path).stem, item_type, "fail", 0.0, duration_s,
                run_id=run_id, tokens_per_minute=final_velocity,
            )
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
    verification_notes: Optional[str] = result.get("verification_notes")

    cumulative_cost_usd[0] += cost_usd

    item_slug = Path(claimed_path).stem

    if success:
        logger.info(
            "Worker PID %d: success. item=%s cost=$%.4f duration=%.1fs",
            pid,
            item_path,
            cost_usd,
            duration_s,
        )
        get_dashboard_state().remove_active_worker(pid, "success", cost_usd, duration_s)
        proxy = get_proxy()
        if proxy is not None:
            proxy.record_completion(
                item_slug, item_type, "success", cost_usd, duration_s,
                run_id=run_id, tokens_per_minute=final_velocity,
                verification_notes=verification_notes,
            )
        # Reset warn counter on success.
        if warn_counts is not None:
            warn_counts.pop(item_slug, None)
    else:
        # Handled failure — track warn count to cap retries.
        if warn_counts is not None:
            warn_counts[item_slug] = warn_counts.get(item_slug, 0) + 1
            current_warns = warn_counts[item_slug]
        else:
            current_warns = 1

        failure_msg = (
            f"Worker PID {pid}: handled failure. item={item_path} "
            f"cost=${cost_usd:.4f} duration={duration_s:.1f}s "
            f"warns={current_warns}/{MAX_WARN_RETRIES_PER_ITEM} message={message}"
        )
        logger.warning(failure_msg)
        get_dashboard_state().add_notification(failure_msg)
        get_dashboard_state().remove_active_worker(pid, "warn", cost_usd, duration_s)
        proxy = get_proxy()
        if proxy is not None:
            proxy.record_completion(
                item_slug, item_type, "warn", cost_usd, duration_s,
                run_id=run_id, tokens_per_minute=final_velocity,
                verification_notes=verification_notes,
            )

        if current_warns >= MAX_WARN_RETRIES_PER_ITEM:
            exhausted_msg = (
                f"Item {item_slug} exhausted after {current_warns} consecutive "
                f"warn completions — archiving instead of retrying."
            )
            logger.error(exhausted_msg)
            get_dashboard_state().add_notification(exhausted_msg)
            if slack is not None:
                slack.send_status(exhausted_msg, level="warning")
            # Leave in .claimed/ — the archive node will pick it up,
            # or the next startup will unclaim orphans.
        else:
            try:
                unclaim_item(claimed_path, item_type)
                logger.info("Unclaimed %s back to %s backlog.", claimed_path, item_type)
            except Exception as exc:
                logger.error(
                    "Failed to unclaim %s after worker failure: %s", claimed_path, exc
                )

    if budget_cap_usd is not None and cumulative_cost_usd[0] >= budget_cap_usd:
        logger.warning(
            "Budget cap reached: cumulative=$%.4f >= cap=$%.2f",
            cumulative_cost_usd[0],
            budget_cap_usd,
        )
        if slack is not None:
            slack.send_status(
                f"Budget cap ${budget_cap_usd:.2f} USD reached "
                f"(spent ${cumulative_cost_usd[0]:.4f}). "
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
    warn_counts: Optional[dict[str, int]] = None,
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
        if _reap_one_worker(pid, record, cumulative_cost_usd, budget_cap_usd, slack, warn_counts):
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

    item_path, item_slug, item_type, plan_path, resume_pid = candidate

    claimed = claim_item(item_path, item_type)
    if not claimed:
        logger.debug("Lost claim race on %s — another process claimed it.", item_path)
        return False

    claimed_path = os.path.join(CLAIMED_DIR, os.path.basename(item_path))
    result_file = _make_result_file_path()

    try:
        proc = _spawn_worker(claimed_path, result_file, item_type, item_slug, resume_pid=resume_pid)
        pid = proc.pid
        # Store the checkpoint PID (the DB being used), not the worker's own PID.
        # For resume workers, that's the resume_pid so the chain is preserved.
        checkpoint_pid = resume_pid if resume_pid is not None else pid
        _save_worker_pid_to_sidecar(claimed_path, checkpoint_pid)
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


# ─── Run-id and token refresh ─────────────────────────────────────────────────


def _refresh_worker_run_ids(active_workers: dict[int, WorkerRecord]) -> None:
    """Re-read item files for active workers that still have no LangSmith run_id.

    For freshly dispatched workers the trace ID is not yet written to the item
    file when the supervisor registers them. This function is called each poll
    iteration so that once the subprocess writes ``## LangSmith Trace: <uuid>``
    the dashboard can surface the "View Traces" link without waiting for the
    worker to finish.

    Args:
        active_workers: Current mapping of pid → WorkerRecord.
    """
    dashboard = get_dashboard_state()
    with dashboard._lock:
        missing_run_id_pids = [
            pid
            for pid, worker_info in dashboard.active_workers.items()
            if worker_info.run_id is None and pid in active_workers
        ]

    for pid in missing_run_id_pids:
        record = active_workers.get(pid)
        if record is None:
            continue
        claimed_path = record[0]
        run_id = read_trace_id_from_file(claimed_path)
        if run_id is not None:
            dashboard.update_worker_run_id(pid, run_id)
            logger.debug(
                "Refreshed run_id for worker PID %d: %s", pid, run_id
            )


def _refresh_worker_token_counts(active_workers: dict[int, WorkerRecord]) -> None:
    """Update token counts for all active workers that have a known run_id.

    Called each poll iteration after _refresh_worker_run_ids(). Queries
    the traces DB via the proxy for each worker with a non-None run_id and
    writes the updated counts to DashboardState so the SSE snapshot can
    compute tokens_per_minute.

    Args:
        active_workers: Current mapping of pid → WorkerRecord.
    """
    proxy = get_proxy()
    if proxy is None:
        return

    dashboard = get_dashboard_state()
    with dashboard._lock:
        workers_with_run_id = [
            (pid, worker_info.run_id)
            for pid, worker_info in dashboard.active_workers.items()
            if worker_info.run_id is not None and pid in active_workers
        ]

    for pid, run_id in workers_with_run_id:
        tokens_in, tokens_out = proxy.get_worker_token_counts(run_id)
        dashboard.update_worker_tokens(pid, tokens_in, tokens_out)
        # Record sample for velocity history.
        with dashboard._lock:
            worker = dashboard.active_workers.get(pid)
            if worker is not None:
                worker.record_token_sample()


# ─── Main supervisor loop ─────────────────────────────────────────────────────


def run_supervisor_loop(
    max_workers: int,
    budget_cap_usd: Optional[float],
    dry_run: bool,
    shutdown_event: threading.Event,
    slack: Optional[SlackNotifier],
    code_monitor: Optional["CodeChangeMonitor"] = None,
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
            f"${budget_cap_usd:.2f}" if budget_cap_usd is not None else "none",
        )
        while not shutdown_event.is_set():
            logger.info("[DRY RUN] Would dispatch up to %d workers.", max_workers)
            shutdown_event.wait(SCAN_SLEEP_SECONDS)
        logger.info("Shutdown event set — exiting dry-run supervisor loop.")
        return EXIT_CODE_CLEAN

    active_workers: dict[int, WorkerRecord] = {}
    cumulative_cost_usd: list[float] = [0.0]
    budget_exceeded = False
    # Track consecutive warn completions per item slug to cap retries.
    warn_counts: dict[str, int] = {}

    # Cleanup: return any items orphaned in CLAIMED_DIR by a previous run,
    # then delete any plan YAMLs that have no corresponding active item.
    _unclaim_orphaned_items()
    _cleanup_orphaned_plan_yamls()

    logger.info(
        "Supervisor starting: max_workers=%d budget_cap=%s",
        max_workers,
        f"${budget_cap_usd:.2f} USD" if budget_cap_usd is not None else "none",
    )

    try:
        while not shutdown_event.is_set():
            ideas_processed = process_ideas(dry_run)
            if ideas_processed > 0:
                logger.info("Ideas intake: processed %d idea(s)", ideas_processed)
            # Step 1: Reap any finished workers (non-blocking).
            if active_workers:
                budget_exceeded = _reap_finished_workers(
                    active_workers, cumulative_cost_usd, budget_cap_usd, slack,
                    warn_counts,
                )

            # Step 1b: Refresh run_ids for workers that launched without one.
            if active_workers:
                _refresh_worker_run_ids(active_workers)

            # Token counts are now updated by workers via POST /api/worker-stats.
            # No need for supervisor-side DB polling.

            # Step 1d: Check if any worker reported quota exhaustion.
            dashboard = get_dashboard_state()
            if dashboard.quota_exhausted:
                if active_workers:
                    logger.warning("Quota exhausted — waiting for %d active worker(s) to finish before entering probe loop.",
                                   len(active_workers))
                else:
                    logger.warning("Quota exhausted — entering probe loop.")
                    from langgraph_pipeline.shared.quota import probe_quota_available
                    while not shutdown_event.is_set():
                        shutdown_event.wait(300)  # 5-minute probe interval
                        if shutdown_event.is_set():
                            break
                        if probe_quota_available():
                            logger.info("Quota probe succeeded — resuming pipeline.")
                            dashboard.quota_exhausted = False
                            if slack is not None:
                                slack.send_status("Claude quota restored — pipeline resuming.", level="info")
                            break
                        logger.warning("Quota probe failed — still exhausted.")

            # Step 2: Dispatch new workers while slots are available.
            if not budget_exceeded and not dashboard.quota_exhausted and not shutdown_event.is_set():
                while len(active_workers) < max_workers and not shutdown_event.is_set():
                    dispatched = _try_dispatch_one(active_workers)
                    if not dispatched:
                        break  # Backlog empty or claim lost; don't spin.

            # Step 3: Hot-reload check — restart when no workers are active.
            if code_monitor is not None and code_monitor.restart_pending.is_set():
                if not active_workers:
                    logger.info("Code change detected and no active workers — restarting.")
                    _perform_restart(code_monitor)
                else:
                    logger.info(
                        "Code change detected — waiting for %d active worker(s) to finish before restart.",
                        len(active_workers),
                    )

            # Step 4: Sleep strategy depends on whether workers are active.
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

        # If a hot-reload restart was pending, honour it now that workers are drained.
        if code_monitor is not None and code_monitor.restart_pending.is_set():
            logger.info("Workers drained — performing deferred hot-reload restart.")
            _perform_restart(code_monitor)

        logger.info(
            "Supervisor exiting. Total cumulative cost: $%.4f USD.",
            cumulative_cost_usd[0],
        )

        if budget_exceeded:
            return EXIT_CODE_BUDGET_EXHAUSTED
        return EXIT_CODE_CLEAN

    except Exception as exc:
        logger.exception("Unhandled error in supervisor loop: %s", exc)
        return EXIT_CODE_ERROR
