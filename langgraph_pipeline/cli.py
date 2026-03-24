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
import logging
import os
import signal
import sys
import threading
import time
from typing import Optional

from langgraph_pipeline.pipeline.graph import PIPELINE_THREAD_ID, pipeline_graph
from langgraph_pipeline.pipeline.nodes.scan import scan_backlog as scan_backlog_fn
from langgraph_pipeline.pipeline.state import PipelineState
from langgraph_pipeline.shared.claude_cli import call_claude
from langgraph_pipeline.shared.config import load_orchestrator_config
from langgraph_pipeline.shared.dotenv import load_dotenv_files
from langgraph_pipeline.shared.langsmith import configure_tracing
from langgraph_pipeline.shared.paths import LANGGRAPH_PID_FILE_PATH
from langgraph_pipeline.shared.quota import QUOTA_PROBE_INTERVAL_SECONDS, probe_quota_available
from langgraph_pipeline.slack import SlackNotifier

# ─── Constants ────────────────────────────────────────────────────────────────

VERSION = "1.8.1"

EXIT_CODE_CLEAN = 0
EXIT_CODE_ERROR = 1
EXIT_CODE_BUDGET_EXHAUSTED = 2

SCAN_SLEEP_SECONDS = 15
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


def _log_startup_banner(args: argparse.Namespace, config: dict) -> None:
    """Log a startup banner summarising version and active configuration.

    Args:
        args: Parsed CLI arguments.
        config: Loaded orchestrator config dict.
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


# ─── Continuous scan loop ─────────────────────────────────────────────────────


def _run_scan_loop(
    budget_cap_usd: Optional[float],
    dry_run: bool,
    shutdown_event: threading.Event,
    slack: Optional[SlackNotifier] = None,
) -> int:
    """Run the continuous scan loop until shutdown or budget exhaustion.

    Opens the pipeline_graph() context manager once and invokes the graph
    repeatedly. Sleeps between iterations when no item was found. Checks the
    shutdown event and budget cap between each invocation. Enters the quota
    probe idle loop when quota exhaustion is detected.

    Args:
        budget_cap_usd: Budget cap in USD, or None.
        dry_run: When True, log each iteration without executing.
        shutdown_event: Set by signal handlers to request clean exit.
        slack: SlackNotifier instance, or None if Slack is disabled.

    Returns:
        EXIT_CODE_CLEAN on graceful shutdown,
        EXIT_CODE_BUDGET_EXHAUSTED when cap is reached,
        EXIT_CODE_ERROR on unhandled exception.
    """
    if dry_run:
        logger.info("[DRY RUN] Continuous scan loop — no graph invocations will be made.")
        while not shutdown_event.is_set():
            logger.info("[DRY RUN] Would invoke pipeline_graph() for next backlog item.")
            shutdown_event.wait(SCAN_SLEEP_SECONDS)
        logger.info("Shutdown event set — exiting dry-run loop.")
        return EXIT_CODE_CLEAN

    try:
        thread_config = {"configurable": {"thread_id": PIPELINE_THREAD_ID}}

        with pipeline_graph() as graph:
            while not shutdown_event.is_set():
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

                if shutdown_event.is_set():
                    break

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
    _log_startup_banner(args, config)

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
            )
    finally:
        _remove_pid_file()
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
