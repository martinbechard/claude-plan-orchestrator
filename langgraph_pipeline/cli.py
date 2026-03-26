#!/usr/bin/env -S python3 -u
# langgraph_pipeline/cli.py
# CLI entry point for the unified LangGraph pipeline runner.
# Design: docs/plans/2026-02-26-20-unified-langgraph-runner-design.md

"""Unified LangGraph pipeline runner.

Single CLI entry point that runs the complete LangGraph pipeline graph,
replacing both auto-pipeline.py (backlog scanning, intake, verification loop)
and plan-orchestrator.py (task execution) with one invocation.

Usage:
    python -m langgraph_pipeline [--budget-cap N] [--dry-run]
        [--single-item PATH] [--backlog-dir DIR] [--log-level LEVEL]
        [--no-slack] [--no-tracing]

Exit codes:
    0 -- clean shutdown (SIGINT/SIGTERM or single-item complete)
    1 -- unhandled error
    2 -- budget exhausted
"""

import argparse
import glob
import json
import logging
import os
import signal
import sys
import threading
import time
from typing import Optional

import yaml

from langgraph_pipeline.pipeline.graph import PIPELINE_THREAD_ID, pipeline_graph
from langgraph_pipeline.pipeline.nodes.idea_classifier import process_ideas
from langgraph_pipeline.pipeline.nodes.scan import scan_backlog as scan_backlog_fn
from langgraph_pipeline.pipeline.state import PipelineState
from langgraph_pipeline.shared.claude_cli import call_claude
from langgraph_pipeline.shared.config import get_max_parallel_items, load_orchestrator_config
from langgraph_pipeline.shared.dotenv import load_dotenv_files
from langgraph_pipeline.shared.langsmith import configure_tracing
from langgraph_pipeline.shared.paths import LANGGRAPH_PID_FILE_PATH
from langgraph_pipeline.shared.suspension import SUSPENDED_DIR, clear_suspension_marker
from langgraph_pipeline.shared.hot_reload import CodeChangeMonitor, _perform_restart
from langgraph_pipeline.shared.quota import QUOTA_PROBE_INTERVAL_SECONDS, probe_quota_available
from langgraph_pipeline.slack import SlackNotifier
from langgraph_pipeline.supervisor import run_supervisor_loop

# ─── Constants ────────────────────────────────────────────────────────────────

VERSION = "1.8.1"

EXIT_CODE_CLEAN = 0
EXIT_CODE_ERROR = 1
EXIT_CODE_BUDGET_EXHAUSTED = 2

SCAN_SLEEP_SECONDS = 15
SUSPENDED_GLOB = os.path.join(SUSPENDED_DIR, "*.json")
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# ─── Logging ──────────────────────────────────────────────────────────────────

logger = logging.getLogger(__name__)


def _configure_logging(level_name: str) -> None:
    """Configure root logging with the specified level."""
    level = getattr(logging, level_name.upper(), logging.INFO)
    logging.basicConfig(format=LOG_FORMAT, datefmt=LOG_DATE_FORMAT, level=level)


# ─── Argument parsing ─────────────────────────────────────────────────────────


def _build_arg_parser() -> argparse.ArgumentParser:
    """Build and return the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Unified LangGraph pipeline runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--budget-cap",
        type=float,
        default=None,
        metavar="USD",
        help="Stop after cumulative session cost exceeds this value (USD). "
        "Exits with code 2. Default: no cap.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Log what would be done without executing graph nodes.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        default=False,
        help="Scan the backlog, process one item, then exit. "
        "Equivalent to the old auto-pipeline.py --once flag.",
    )
    parser.add_argument(
        "--single-item",
        metavar="PATH",
        default=None,
        help="Process exactly one backlog item at PATH and exit with code 0.",
    )
    parser.add_argument(
        "--backlog-dir",
        metavar="DIR",
        default=None,
        help="Override the backlog directory scanned for new items.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity level. Default: INFO.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="Shorthand for --log-level DEBUG.",
    )
    parser.add_argument(
        "--no-slack",
        action="store_true",
        default=False,
        help="Disable all Slack notifications and polling.",
    )
    parser.add_argument(
        "--no-tracing",
        action="store_true",
        default=False,
        help="Skip LangSmith tracing configuration.",
    )
    parser.add_argument(
        "--web",
        action="store_true",
        default=False,
        help="Start the embedded web UI (dashboard, proxy, analysis) on --web-port.",
    )
    parser.add_argument(
        "--web-port",
        type=int,
        default=None,
        metavar="PORT",
        help="Port for the embedded web UI. Default: 7070.",
    )
    return parser


# ─── PID file management ─────────────────────────────────────────────────────


def _write_pid_file() -> None:
    """Write the current process PID to LANGGRAPH_PID_FILE_PATH."""
    try:
        with open(LANGGRAPH_PID_FILE_PATH, "w") as f:
            f.write(str(os.getpid()))
        logger.debug("PID file written: %s (PID %d)", LANGGRAPH_PID_FILE_PATH, os.getpid())
    except OSError as exc:
        logger.warning("Could not write PID file %s: %s", LANGGRAPH_PID_FILE_PATH, exc)


def _remove_pid_file() -> None:
    """Remove LANGGRAPH_PID_FILE_PATH on shutdown (safe to call if missing)."""
    try:
        os.remove(LANGGRAPH_PID_FILE_PATH)
        logger.debug("PID file removed: %s", LANGGRAPH_PID_FILE_PATH)
    except FileNotFoundError:
        pass
    except OSError as exc:
        logger.warning("Could not remove PID file %s: %s", LANGGRAPH_PID_FILE_PATH, exc)


def _check_stale_pid() -> None:
    """Warn if a stale PID file exists from a previous run.

    Reads the stored PID and checks whether the process is alive. Logs a
    warning if another LangGraph pipeline instance appears to be running.
    Does not block startup; the caller decides whether to proceed.
    """
    try:
        with open(LANGGRAPH_PID_FILE_PATH, "r") as f:
            stored_pid = int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return  # No PID file or unreadable -- nothing to check.

    try:
        os.kill(stored_pid, 0)  # signal 0 = check existence without sending signal
        logger.warning(
            "PID file %s exists with PID %d which appears to be alive. "
            "Another LangGraph pipeline instance may be running. Proceeding anyway.",
            LANGGRAPH_PID_FILE_PATH,
            stored_pid,
        )
    except ProcessLookupError:
        logger.debug("Stale PID file found (PID %d is dead). Overwriting.", stored_pid)
    except PermissionError:
        logger.warning(
            "PID file %s exists with PID %d (permission denied to signal -- "
            "may be running as another user).",
            LANGGRAPH_PID_FILE_PATH,
            stored_pid,
        )


# ─── Signal handling ──────────────────────────────────────────────────────────


def _register_signal_handlers(shutdown_event: threading.Event) -> None:
    """Register SIGINT and SIGTERM handlers that set the shutdown event.

    The current graph invocation completes before the runner exits; the
    shutdown_event is only checked between iterations.

    Args:
        shutdown_event: Event set by the handler to request clean shutdown.
    """

    def _handler(signum: int, frame: object) -> None:
        sig_name = "SIGINT" if signum == signal.SIGINT else "SIGTERM"
        logger.info(
            "Received %s — will stop after current graph invocation completes.", sig_name
        )
        shutdown_event.set()

    signal.signal(signal.SIGINT, _handler)
    signal.signal(signal.SIGTERM, _handler)


# ─── Startup banner ───────────────────────────────────────────────────────────


def _log_startup_banner(
    args: argparse.Namespace, config: dict, max_parallel_items: int
) -> None:
    """Log a startup banner summarising version and active configuration.

    Args:
        args: Parsed CLI arguments.
        config: Loaded orchestrator config dict.
        max_parallel_items: Number of parallel workers from config.
    """
    logger.info("=" * 60)
    logger.info("LangGraph Pipeline Runner v%s", VERSION)
    logger.info("=" * 60)
    mode = "single-item" if args.single_item else "once" if args.once else "continuous scan"
    logger.info("Mode          : %s", mode)
    if args.single_item:
        logger.info("Item path     : %s", args.single_item)
    if args.backlog_dir:
        logger.info("Backlog dir   : %s", args.backlog_dir)
    logger.info(
        "Budget cap    : %s",
        f"~${args.budget_cap:.2f} USD" if args.budget_cap is not None else "none",
    )
    logger.info("Dry run       : %s", "yes" if args.dry_run else "no")
    logger.info("Slack         : %s", "disabled" if args.no_slack else "enabled")
    logger.info("Tracing       : %s", "disabled" if args.no_tracing else "enabled")
    logger.info("Log level     : %s", args.log_level)
    project_name = config.get("project_name", "(not configured)")
    logger.info("Project       : %s", project_name)
    if max_parallel_items > 1:
        logger.info("Workers       : %d", max_parallel_items)
    if not args.single_item and not args.once:
        logger.info("Hot-reload    : active (watching source files)")
    logger.info("=" * 60)


# ─── Budget check ─────────────────────────────────────────────────────────────


def _is_budget_exhausted(state: PipelineState, budget_cap_usd: Optional[float]) -> bool:
    """Return True if session cost exceeds the budget cap.

    Args:
        state: Returned pipeline state after graph.invoke().
        budget_cap_usd: Cap in USD, or None for no limit.

    Returns:
        True when cost >= cap and cap is set.
    """
    if budget_cap_usd is None:
        return False
    cost = state.get("session_cost_usd", 0.0)
    if cost >= budget_cap_usd:
        logger.warning(
            "Budget cap exhausted: session_cost_usd=~$%.4f >= cap=~$%.2f",
            cost,
            budget_cap_usd,
        )
        return True
    return False


# ─── Quota probe idle loop ────────────────────────────────────────────────────


def _run_quota_probe_loop(
    shutdown_event: threading.Event,
    slack: Optional[SlackNotifier],
) -> None:
    """Block until Claude quota is available again or shutdown is requested.

    Logs a warning and sends an optional Slack notification on entry, then
    probes Claude every QUOTA_PROBE_INTERVAL_SECONDS seconds until either a
    successful response is received or the shutdown event is set.

    Args:
        shutdown_event: Set by signal handlers to request clean exit.
        slack: SlackNotifier instance, or None if Slack is disabled.
    """
    logger.warning(
        "Quota exhausted — entering probe loop. "
        "Will retry every %ds until Claude responds.",
        QUOTA_PROBE_INTERVAL_SECONDS,
    )
    if slack is not None:
        slack.send_status(
            "Claude quota exhausted — pipeline paused. "
            f"Probing every {QUOTA_PROBE_INTERVAL_SECONDS}s.",
            level="warning",
        )

    while not shutdown_event.is_set():
        shutdown_event.wait(QUOTA_PROBE_INTERVAL_SECONDS)
        if shutdown_event.is_set():
            break
        if probe_quota_available():
            logger.info("Quota probe succeeded — resuming pipeline.")
            if slack is not None:
                slack.send_status("Claude quota restored — pipeline resuming.", level="info")
            break
        logger.warning(
            "Quota probe failed — still exhausted. Retrying in %ds.",
            QUOTA_PROBE_INTERVAL_SECONDS,
        )


# ─── Lightweight pre-scan ─────────────────────────────────────────────────────


def _pre_scan(budget_cap_usd: Optional[float]) -> Optional[PipelineState]:
    """Run scan_backlog directly (no graph, no tracing) to check for work.

    Returns a PipelineState with the item pre-populated if work was found,
    or None if the backlog is empty. This avoids sending LangSmith traces
    for idle scan cycles.
    """
    empty_state = _build_initial_state(budget_cap_usd)
    scan_result = scan_backlog_fn(empty_state)

    item_path = scan_result.get("item_path", "")
    if not item_path:
        return None

    # Merge scan results into initial state so the graph skips scan_backlog.
    state = _build_initial_state(budget_cap_usd, item_path=item_path)
    state["item_slug"] = scan_result.get("item_slug", "")
    state["item_type"] = scan_result.get("item_type", "feature")
    state["item_name"] = scan_result.get("item_name", "")
    state["plan_path"] = scan_result.get("plan_path")
    return state


# ─── Initial state builders ───────────────────────────────────────────────────


def _build_initial_state(
    budget_cap_usd: Optional[float],
    item_path: Optional[str] = None,
) -> PipelineState:
    """Build the initial PipelineState for a graph invocation.

    Args:
        budget_cap_usd: Budget cap to embed in state, or None.
        item_path: When set, populates item_path so scan_backlog is bypassed.

    Returns:
        Minimal PipelineState dict sufficient to start the graph.
    """
    state: PipelineState = {
        "item_path": item_path or "",
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
        "budget_cap_usd": budget_cap_usd,
        "session_cost_usd": 0.0,
        "session_input_tokens": 0,
        "session_output_tokens": 0,
        "intake_count_defects": 0,
        "intake_count_features": 0,
    }
    return state


# ─── Single-item mode ─────────────────────────────────────────────────────────


def _run_single_item(
    item_path: str,
    budget_cap_usd: Optional[float],
    dry_run: bool,
) -> int:
    """Invoke the pipeline graph for one specific item and return an exit code.

    Args:
        item_path: Path to the backlog item to process.
        budget_cap_usd: Budget cap in USD, or None.
        dry_run: When True, log the invocation without executing.

    Returns:
        EXIT_CODE_CLEAN on success, EXIT_CODE_BUDGET_EXHAUSTED if cap exceeded,
        EXIT_CODE_ERROR on unhandled exception.
    """
    logger.info("Single-item mode: processing %s", item_path)
    if dry_run:
        logger.info("[DRY RUN] Would invoke pipeline_graph() for item: %s", item_path)
        return EXIT_CODE_CLEAN

    try:
        initial_state = _build_initial_state(budget_cap_usd, item_path=item_path)
        thread_config = {"configurable": {"thread_id": PIPELINE_THREAD_ID}}

        with pipeline_graph() as graph:
            final_state: PipelineState = graph.invoke(initial_state, config=thread_config)

        if final_state.get("quota_exhausted"):
            logger.warning(
                "Quota exhausted during single-item run — item left in backlog for retry."
            )
            return EXIT_CODE_CLEAN

        logger.info(
            "Item complete: cost=~$%.4f tokens_in=%d tokens_out=%d",
            final_state.get("session_cost_usd", 0.0),
            final_state.get("session_input_tokens", 0),
            final_state.get("session_output_tokens", 0),
        )

        if _is_budget_exhausted(final_state, budget_cap_usd):
            return EXIT_CODE_BUDGET_EXHAUSTED

        return EXIT_CODE_CLEAN

    except Exception as exc:
        logger.exception("Unhandled error in single-item mode: %s", exc)
        return EXIT_CODE_ERROR


# ─── Once mode (scan + process one item) ──────────────────────────────────────


def _run_once(
    budget_cap_usd: Optional[float],
    dry_run: bool,
) -> int:
    """Scan the backlog, process the first item found, then exit.

    This replicates the old auto-pipeline.py --once behaviour: one scan cycle,
    one item processed, clean exit.  If no item is found, exits cleanly.

    Args:
        budget_cap_usd: Budget cap in USD, or None.
        dry_run: When True, log what would be done without executing.

    Returns:
        EXIT_CODE_CLEAN on success or no items,
        EXIT_CODE_BUDGET_EXHAUSTED if cap exceeded,
        EXIT_CODE_ERROR on unhandled exception.
    """
    logger.info("Once mode: will process one backlog item then exit.")
    if dry_run:
        logger.info("[DRY RUN] Would invoke pipeline_graph() for the next backlog item.")
        return EXIT_CODE_CLEAN

    try:
        # Lightweight pre-scan: no graph, no tracing.
        pre_scanned = _pre_scan(budget_cap_usd)
        if pre_scanned is None:
            logger.info("No backlog items found. Exiting.")
            return EXIT_CODE_CLEAN

        logger.info(
            "Processing [%s] %s",
            pre_scanned.get("item_type"),
            pre_scanned.get("item_slug"),
        )

        thread_config = {"configurable": {"thread_id": PIPELINE_THREAD_ID}}
        with pipeline_graph() as graph:
            final_state: PipelineState = graph.invoke(pre_scanned, config=thread_config)

        if final_state.get("quota_exhausted"):
            logger.warning(
                "Quota exhausted during once-mode run — item left in backlog for retry."
            )
            return EXIT_CODE_CLEAN

        logger.info(
            "Item complete: cost=~$%.4f tokens_in=%d tokens_out=%d",
            final_state.get("session_cost_usd", 0.0),
            final_state.get("session_input_tokens", 0),
            final_state.get("session_output_tokens", 0),
        )

        if _is_budget_exhausted(final_state, budget_cap_usd):
            return EXIT_CODE_BUDGET_EXHAUSTED

        return EXIT_CODE_CLEAN

    except Exception as exc:
        logger.exception("Unhandled error in once mode: %s", exc)
        return EXIT_CODE_ERROR


# ─── Suspension helpers ───────────────────────────────────────────────────────


def _post_pending_suspension_questions(slack: Optional[SlackNotifier]) -> None:
    """Post Slack questions for suspension markers that have not yet been posted.

    Scans SUSPENDED_DIR for marker files where slack_thread_ts is empty and posts
    the question to the appropriate Slack channel. Updates the marker with the
    returned thread_ts and channel_id for reply correlation.

    If slack is None or not enabled, this is a no-op; markers remain for the next cycle.

    Args:
        slack: SlackNotifier instance, or None if Slack is disabled.
    """
    if slack is None or not slack.is_enabled():
        return

    for marker_path in glob.glob(SUSPENDED_GLOB):
        try:
            with open(marker_path) as f:
                marker = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not read suspension marker %s: %s", marker_path, exc)
            continue

        if marker.get("slack_thread_ts"):
            continue  # Already posted to Slack

        slug = marker.get("slug", "")
        item_type = marker.get("item_type", "feature")
        question = marker.get("question", "")
        question_context = marker.get("question_context", "")

        if not slug or not question:
            continue

        thread_ts = slack.post_suspension_question(slug, item_type, question, question_context)
        if thread_ts:
            channel_id = slack.get_type_channel_id(item_type)
            marker["slack_thread_ts"] = thread_ts
            marker["slack_channel_id"] = channel_id
            try:
                with open(marker_path, "w") as f:
                    json.dump(marker, f, indent=2)
                logger.info(
                    "Suspension question posted for %s (thread_ts=%s)", slug, thread_ts
                )
            except OSError as exc:
                logger.warning(
                    "Could not update suspension marker %s: %s", marker_path, exc
                )
        else:
            logger.warning("Failed to post suspension question for %s", slug)


def _reinstate_answered_suspensions() -> None:
    """Reinstate suspended tasks that have received a human answer via Slack.

    Scans SUSPENDED_DIR for marker files where answer is a non-empty string.
    For each answered marker, resets the task to pending in the plan YAML,
    injects human_answer and human_question fields onto the task dict, saves
    the YAML, and deletes the marker file.
    """
    for marker_path in glob.glob(SUSPENDED_GLOB):
        try:
            with open(marker_path) as f:
                marker = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not read suspension marker %s: %s", marker_path, exc)
            continue

        answer = marker.get("answer", "")
        if not isinstance(answer, str) or not answer.strip():
            continue  # Not yet answered

        plan_path = marker.get("plan_path", "")
        task_id = marker.get("task_id", "")
        slug = marker.get("slug", "")

        if not plan_path or not task_id:
            logger.warning(
                "Suspension marker %s missing plan_path or task_id — skipping",
                marker_path,
            )
            continue

        try:
            with open(plan_path) as f:
                plan_data = yaml.safe_load(f)
        except (OSError, yaml.YAMLError) as exc:
            logger.warning("Could not load plan YAML %s: %s", plan_path, exc)
            continue

        task = None
        for section in plan_data.get("sections", []):
            for t in section.get("tasks", []):
                if t.get("id") == task_id:
                    task = t
                    break
            if task is not None:
                break

        if task is None:
            logger.warning(
                "Task %s not found in plan %s — skipping reinstatement",
                task_id,
                plan_path,
            )
            continue

        task["status"] = "pending"
        task["human_answer"] = answer.strip()
        task["human_question"] = marker.get("question", "")

        try:
            with open(plan_path, "w") as f:
                yaml.dump(
                    plan_data, f, default_flow_style=False, sort_keys=False, allow_unicode=True
                )
        except OSError as exc:
            logger.warning("Could not save plan YAML %s: %s", plan_path, exc)
            continue

        clear_suspension_marker(slug)
        logger.info(
            "Reinstated task %s in %s with human answer (slug=%s)", task_id, plan_path, slug
        )


# ─── Continuous scan loop ─────────────────────────────────────────────────────


def _run_scan_loop(
    budget_cap_usd: Optional[float],
    dry_run: bool,
    shutdown_event: threading.Event,
    slack: Optional[SlackNotifier] = None,
    max_parallel_items: int = 1,
) -> int:
    """Run the continuous scan loop until shutdown or budget exhaustion.

    When max_parallel_items > 1, delegates to run_supervisor_loop() which
    dispatches N concurrent worker subprocesses. When max_parallel_items == 1,
    uses the existing sequential single-item graph-invoke loop.

    Args:
        budget_cap_usd: Budget cap in USD, or None.
        dry_run: When True, log each iteration without executing.
        shutdown_event: Set by signal handlers to request clean exit.
        slack: SlackNotifier instance, or None if Slack is disabled.
        max_parallel_items: Number of parallel workers; 1 means sequential mode.

    Returns:
        EXIT_CODE_CLEAN on graceful shutdown,
        EXIT_CODE_BUDGET_EXHAUSTED when cap is reached,
        EXIT_CODE_ERROR on unhandled exception.
    """
    if max_parallel_items > 1:
        return run_supervisor_loop(
            max_workers=max_parallel_items,
            budget_cap_usd=budget_cap_usd,
            dry_run=dry_run,
            shutdown_event=shutdown_event,
            slack=slack,
        )
    if dry_run:
        logger.info("[DRY RUN] Continuous scan loop — no graph invocations will be made.")
        while not shutdown_event.is_set():
            logger.info("[DRY RUN] Would invoke pipeline_graph() for next backlog item.")
            shutdown_event.wait(SCAN_SLEEP_SECONDS)
        logger.info("Shutdown event set — exiting dry-run loop.")
        return EXIT_CODE_CLEAN

    try:
        thread_config = {"configurable": {"thread_id": PIPELINE_THREAD_ID}}
        code_monitor = CodeChangeMonitor()
        code_monitor.start()

        try:
            with pipeline_graph() as graph:
                while not shutdown_event.is_set():
                    _reinstate_answered_suspensions()
                    _post_pending_suspension_questions(slack)
                    ideas_processed = process_ideas(dry_run)
                    if ideas_processed > 0:
                        logger.info(
                            "Ideas intake: processed %d idea(s) into backlog", ideas_processed
                        )
                    # Lightweight pre-scan: no graph, no tracing, just check directories.
                    pre_scanned = _pre_scan(budget_cap_usd)

                    if pre_scanned is None:
                        logger.debug(
                            "No backlog item found. Sleeping %ds before next scan.",
                            SCAN_SLEEP_SECONDS,
                        )
                        shutdown_event.wait(SCAN_SLEEP_SECONDS)
                        continue

                    # Item found — invoke the full graph (with tracing).
                    logger.info(
                        "Processing [%s] %s",
                        pre_scanned.get("item_type"),
                        pre_scanned.get("item_slug"),
                    )

                    final_state: PipelineState = graph.invoke(
                        pre_scanned, config=thread_config
                    )

                    if final_state.get("quota_exhausted"):
                        _run_quota_probe_loop(shutdown_event, slack)
                        if code_monitor.restart_pending.is_set():
                            _perform_restart(code_monitor)
                        continue

                    cost = final_state.get("session_cost_usd", 0.0)
                    logger.debug(
                        "Graph invocation complete: cost=~$%.4f tokens_in=%d tokens_out=%d",
                        cost,
                        final_state.get("session_input_tokens", 0),
                        final_state.get("session_output_tokens", 0),
                    )

                    if _is_budget_exhausted(final_state, budget_cap_usd):
                        return EXIT_CODE_BUDGET_EXHAUSTED

                    if code_monitor.restart_pending.is_set():
                        _perform_restart(code_monitor)

                    if shutdown_event.is_set():
                        break
        finally:
            code_monitor.stop()

        logger.info("Shutdown event set — exiting scan loop.")
        return EXIT_CODE_CLEAN

    except Exception as exc:
        logger.exception("Unhandled error in scan loop: %s", exc)
        return EXIT_CODE_ERROR


# ─── Main ─────────────────────────────────────────────────────────────────────


def main() -> int:
    """Entry point: parse CLI, initialise subsystems, run the pipeline.

    Returns:
        Exit code: EXIT_CODE_CLEAN, EXIT_CODE_ERROR, or EXIT_CODE_BUDGET_EXHAUSTED.
    """
    load_dotenv_files()  # Load .env.local then .env before anything reads os.environ

    parser = _build_arg_parser()
    args = parser.parse_args()

    # --verbose is shorthand for --log-level DEBUG
    if args.verbose:
        args.log_level = "DEBUG"

    _configure_logging(args.log_level)

    config = load_orchestrator_config()
    max_parallel_items = get_max_parallel_items(config)
    _log_startup_banner(args, config, max_parallel_items)

    # Start web server BEFORE configure_tracing() so the tracing redirect to
    # localhost can detect the active port and set LANGCHAIN_ENDPOINT accordingly.
    web_enabled = args.web or (config.get("web", {}).get("enabled", False))
    if web_enabled:
        from langgraph_pipeline.web.server import (
            WEB_SERVER_DEFAULT_PORT,
            find_free_port,
            start_web_server,
            write_port_to_config,
        )
        from langgraph_pipeline.shared.paths import ORCHESTRATOR_CONFIG_PATH

        if args.web_port:
            # Tier 1: CLI flag — ephemeral override, no write-back
            web_port = args.web_port
            start_web_server(port=web_port, config=config)
        elif config.get("web", {}).get("port"):
            # Tier 2: already persisted in config — use it directly
            web_port = config["web"]["port"]
            start_web_server(port=web_port, config=config)
        else:
            # Tier 3: auto-discover a free port, write it back for future runs
            from pathlib import Path as _Path
            _config_path = _Path(ORCHESTRATOR_CONFIG_PATH)
            web_port = find_free_port(WEB_SERVER_DEFAULT_PORT)
            write_port_to_config(web_port, _config_path)
            logger.info(
                "Web server started on port=%d (written to %s)",
                web_port,
                _config_path,
            )
            start_web_server(port=web_port, config=config, config_path=_config_path)

    if not args.no_tracing:
        if configure_tracing():
            logger.info("LangSmith tracing enabled.")
    else:
        logger.info("LangSmith tracing disabled (--no-tracing).")

    slack: Optional[SlackNotifier] = None
    if not args.no_slack:
        try:
            slack = SlackNotifier(call_claude=call_claude)
            if slack.is_enabled():
                slack.start_background_polling()
                logger.info("Slack notifications and polling enabled.")
            else:
                logger.info("Slack configured but not enabled (check slack.local.yaml).")
        except Exception as exc:
            logger.warning("Could not initialise Slack (non-fatal): %s", exc)
            slack = None

    _check_stale_pid()
    _write_pid_file()

    shutdown_event = threading.Event()
    _register_signal_handlers(shutdown_event)

    exit_code = EXIT_CODE_CLEAN
    try:
        if args.single_item:
            exit_code = _run_single_item(
                args.single_item,
                args.budget_cap,
                args.dry_run,
            )
        elif args.once:
            exit_code = _run_once(
                args.budget_cap,
                args.dry_run,
            )
        else:
            exit_code = _run_scan_loop(
                args.budget_cap,
                args.dry_run,
                shutdown_event,
                slack,
                max_parallel_items,
            )
    finally:
        _remove_pid_file()
        if web_enabled:
            from langgraph_pipeline.web.server import stop_web_server
            stop_web_server()
        if slack is not None:
            try:
                slack.stop_background_polling()
            except Exception:
                pass

    if exit_code == EXIT_CODE_BUDGET_EXHAUSTED:
        logger.info("Exiting: budget cap exhausted (exit code %d).", exit_code)
    elif exit_code == EXIT_CODE_ERROR:
        logger.error("Exiting: unhandled error (exit code %d).", exit_code)
    else:
        logger.info("Exiting cleanly (exit code %d).", exit_code)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
