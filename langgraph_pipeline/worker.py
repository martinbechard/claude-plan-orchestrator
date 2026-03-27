#!/usr/bin/env python3
# langgraph_pipeline/worker.py
# Subprocess entry point: runs the pipeline graph for one backlog item and writes a result JSON.
# Design: docs/plans/2026-03-24-06-parallel-item-processing-supervisor-worker-model-design.md

"""Worker subprocess for parallel backlog item processing.

Spawned by the supervisor for each active item. Accepts --item-path and
--result-file CLI arguments, runs the full pipeline graph for that one item,
then writes a JSON result file before exiting.

The result file is always written before exit so the supervisor can distinguish
a crash (no file written) from a handled failure (file with success=false).

Exit codes:
    0 -- item processed successfully
    1 -- item failed or unhandled exception
"""

import argparse
import json
import logging
import os
import sys
import time
from typing import Optional

from langgraph_pipeline.pipeline.graph import PIPELINE_DB_PATH, PIPELINE_THREAD_ID, pipeline_graph
from langgraph_pipeline.pipeline.state import PipelineState
from langgraph_pipeline.shared.dotenv import load_dotenv_files

# ─── Constants ────────────────────────────────────────────────────────────────

EXIT_CODE_SUCCESS = 0
EXIT_CODE_ERROR = 1

LOG_FORMAT = "%(asctime)s [%(levelname)s] [worker-%(process)d] %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Each worker uses a PID-namespaced SQLite DB to avoid checkpoint file contention
# when multiple workers run in parallel.
_WORKER_DB_TEMPLATE = ".claude/pipeline-worker-{pid}.db"

# Each worker uses a PID-namespaced thread ID so it starts a fresh checkpoint
# history rather than resuming the supervisor's pipeline-main thread.
_WORKER_THREAD_ID_TEMPLATE = "worker-{pid}"

# Message written to the result file when the graph completes without setting an
# explicit error message.
_DEFAULT_SUCCESS_MESSAGE = "Item processed successfully"
_DEFAULT_FAILURE_MESSAGE = "Pipeline graph returned without success"

# ─── Logging ──────────────────────────────────────────────────────────────────

logger = logging.getLogger(__name__)


def _configure_logging(level_name: str) -> None:
    """Configure root logging for the worker subprocess."""
    level = getattr(logging, level_name.upper(), logging.INFO)
    logging.basicConfig(format=LOG_FORMAT, datefmt=LOG_DATE_FORMAT, level=level)


# ─── Argument parsing ─────────────────────────────────────────────────────────


def _build_arg_parser() -> argparse.ArgumentParser:
    """Build and return the worker CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Worker subprocess: process one backlog item via the pipeline graph.",
    )
    parser.add_argument(
        "--item-path",
        required=True,
        metavar="PATH",
        help="Path to the backlog item to process (inside .claimed/ when spawned by supervisor).",
    )
    parser.add_argument(
        "--result-file",
        required=True,
        metavar="PATH",
        help="Path where the JSON result will be written before exit.",
    )
    parser.add_argument(
        "--item-type",
        default="feature",
        choices=["defect", "feature", "analysis"],
        help="Type of the backlog item. Forwarded from the supervisor.",
    )
    parser.add_argument(
        "--item-slug",
        default="",
        metavar="SLUG",
        help="Slug of the backlog item. Forwarded from the supervisor.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity level. Default: INFO.",
    )
    return parser


# ─── State builder ────────────────────────────────────────────────────────────


def _build_initial_state(item_path: str, item_type: str, item_slug: str) -> PipelineState:
    """Build the initial PipelineState for the worker's graph invocation.

    Workers receive no budget cap — the supervisor enforces the budget after
    reading each worker result. item_type and item_slug are forwarded from the
    supervisor rather than re-derived from the path, because the claimed path
    no longer contains the original backlog directory name.

    Args:
        item_path: Path to the backlog item being processed (inside .claimed/).
        item_type: Type of the backlog item (defect, feature, analysis).
        item_slug: Slug of the backlog item derived from the original filename.

    Returns:
        PipelineState with item_path, item_slug, item_type populated.
    """
    state: PipelineState = {
        "item_path": item_path,
        "item_slug": item_slug,
        "item_type": item_type,
        "item_name": item_slug.replace("-", " ").title(),
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


# ─── Result file ──────────────────────────────────────────────────────────────


def _write_result(
    result_file: str,
    *,
    success: bool,
    item_path: str,
    cost_usd: float,
    input_tokens: int,
    output_tokens: int,
    duration_s: float,
    message: str,
    verification_notes: Optional[str] = None,
) -> None:
    """Write the JSON result file read by the supervisor after waitpid().

    Always called before the worker exits so the supervisor can distinguish a
    crash (no file) from a handled failure (file with success=false).

    Args:
        result_file: Destination path for the JSON file.
        success: True when the item completed without error.
        item_path: Original item path passed to this worker.
        cost_usd: Total API cost for this invocation.
        input_tokens: Total input tokens consumed.
        output_tokens: Total output tokens produced.
        duration_s: Wall-clock seconds from start to finish.
        message: Human-readable summary of the outcome.
        verification_notes: JSON string with verdict, findings[], and evidence from the validator.
    """
    result = {
        "success": success,
        "item_path": item_path,
        "cost_usd": cost_usd,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "duration_s": duration_s,
        "message": message,
        "verification_notes": verification_notes,
    }
    try:
        with open(result_file, "w") as f:
            json.dump(result, f, indent=2)
        logger.debug("Result written to %s (success=%s)", result_file, success)
    except OSError as exc:
        # Log but do not raise — the result file may be missing, which is
        # treated by the supervisor as a crash. That's worse than a partial
        # write, but there is nothing else we can do here.
        logger.error("Could not write result file %s: %s", result_file, exc)


# ─── Worker DB cleanup ────────────────────────────────────────────────────────


def _cleanup_worker_db(db_path: str) -> None:
    """Remove the per-worker SQLite checkpoint DB after a successful run.

    On failure the DB is left intact so the run can be debugged. On success
    it is cleaned up to avoid accumulating stale checkpoint files.

    Args:
        db_path: Path to the SQLite file to remove.
    """
    for suffix in ("", "-shm", "-wal"):
        path = db_path + suffix
        try:
            os.remove(path)
            logger.debug("Removed worker checkpoint file: %s", path)
        except FileNotFoundError:
            pass
        except OSError as exc:
            logger.warning("Could not remove worker checkpoint file %s: %s", path, exc)


# ─── Main ─────────────────────────────────────────────────────────────────────


def main() -> int:
    """Parse CLI arguments, run the pipeline graph for one item, write result.

    Returns:
        EXIT_CODE_SUCCESS (0) on success, EXIT_CODE_ERROR (1) on failure.
    """
    load_dotenv_files()

    parser = _build_arg_parser()
    args = parser.parse_args()

    _configure_logging(args.log_level)

    pid = os.getpid()
    item_path: str = args.item_path
    item_type: str = args.item_type
    item_slug: str = args.item_slug
    result_file: str = args.result_file
    db_path: str = _WORKER_DB_TEMPLATE.format(pid=pid)
    thread_id: str = _WORKER_THREAD_ID_TEMPLATE.format(pid=pid)

    logger.info("Worker started: item=%s result=%s db=%s", item_path, result_file, db_path)

    start_time = time.monotonic()
    final_state: Optional[PipelineState] = None

    try:
        initial_state = _build_initial_state(item_path, item_type, item_slug)
        thread_config = {"configurable": {"thread_id": thread_id}}
        if item_slug:
            thread_config["run_name"] = item_slug

        with pipeline_graph(db_path=db_path) as graph:
            final_state = graph.invoke(initial_state, config=thread_config)

        duration_s = time.monotonic() - start_time
        cost_usd = final_state.get("session_cost_usd", 0.0)
        input_tokens = final_state.get("session_input_tokens", 0)
        output_tokens = final_state.get("session_output_tokens", 0)

        from langgraph_pipeline.shared.claude_cli import is_quota_exhausted
        if final_state.get("quota_exhausted") or is_quota_exhausted():
            logger.warning("Worker: quota exhausted during item processing — reporting failure.")
            _write_result(
                result_file,
                success=False,
                item_path=item_path,
                cost_usd=cost_usd,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                duration_s=duration_s,
                message="Claude quota exhausted — item left for retry",
            )
            _cleanup_worker_db(db_path)
            return EXIT_CODE_ERROR

        logger.info(
            "Worker complete: cost=$%.4f tokens_in=%d tokens_out=%d duration=%.1fs",
            cost_usd,
            input_tokens,
            output_tokens,
            duration_s,
        )

        # Check validation verdict from executor
        verdict = final_state.get("last_validation_verdict")
        if verdict == "FAIL":
            outcome_success = False
            outcome_message = "Completed with validation FAIL"
        elif verdict == "WARN":
            outcome_success = False
            outcome_message = "Completed with validation WARN"
        else:
            outcome_success = True
            outcome_message = _DEFAULT_SUCCESS_MESSAGE

        _write_result(
            result_file,
            success=outcome_success,
            item_path=item_path,
            cost_usd=cost_usd,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_s=duration_s,
            message=outcome_message,
            verification_notes=final_state.get("verification_notes"),
        )

        _cleanup_worker_db(db_path)
        return EXIT_CODE_SUCCESS

    except Exception as exc:
        duration_s = time.monotonic() - start_time
        logger.exception("Worker: unhandled exception for item %s: %s", item_path, exc)

        cost_usd = 0.0
        input_tokens = 0
        output_tokens = 0
        if final_state is not None:
            cost_usd = final_state.get("session_cost_usd", 0.0)
            input_tokens = final_state.get("session_input_tokens", 0)
            output_tokens = final_state.get("session_output_tokens", 0)

        _write_result(
            result_file,
            success=False,
            item_path=item_path,
            cost_usd=cost_usd,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration_s=duration_s,
            message=f"Unhandled exception: {exc}",
        )
        return EXIT_CODE_ERROR


if __name__ == "__main__":
    sys.exit(main())
