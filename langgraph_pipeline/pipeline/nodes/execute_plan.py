# langgraph_pipeline/pipeline/nodes/execute_plan.py
# execute_plan LangGraph node: subprocess bridge to plan-orchestrator.py.
# Design: docs/plans/2026-02-26-04-pipeline-graph-nodes-design.md

"""execute_plan node for the pipeline StateGraph.

Spawns plan-orchestrator.py as a subprocess to execute a YAML plan, mirroring
the behavior of the execute_plan() function in auto-pipeline.py.

After the subprocess completes, reads the usage report JSON written by
plan-orchestrator.py (at .claude/plans/logs/{plan-name}-usage-report.json)
to extract cost and token data and persist it in PipelineState.

Rate limit detection: if the orchestrator's combined output contains a Claude
rate limit message, the node sets rate_limited/rate_limit_reset in state so
the graph can sleep and retry.
"""

import json
import os
import subprocess
from pathlib import Path
from typing import Optional

import yaml

from langgraph_pipeline.pipeline.state import PipelineState
from langgraph_pipeline.shared.paths import TASK_LOG_DIR
from langgraph_pipeline.shared.rate_limit import check_rate_limit

# ─── Constants ────────────────────────────────────────────────────────────────

PLAN_ORCHESTRATOR_SCRIPT = "scripts/plan-orchestrator.py"
PYTHON_BINARY = "python"

# Maximum characters from the plan name used in usage report filenames.
MAX_PLAN_NAME_LENGTH = 50

# ─── Helpers ──────────────────────────────────────────────────────────────────


def _read_plan_name(plan_path: str) -> str:
    """Read the plan name from a YAML plan file's meta.name field."""
    try:
        with open(plan_path, "r") as f:
            plan = yaml.safe_load(f)
        if plan and isinstance(plan, dict):
            return plan.get("meta", {}).get("name", "unknown")
    except (IOError, yaml.YAMLError):
        pass
    return "unknown"


def _usage_report_path(plan_path: str) -> Path:
    """Return the expected usage report path for the given plan."""
    plan_name = _read_plan_name(plan_path)
    safe_name = plan_name.lower().replace(" ", "-")[:MAX_PLAN_NAME_LENGTH]
    return TASK_LOG_DIR / f"{safe_name}-usage-report.json"


def _read_usage_report(report_path: Path) -> dict[str, float | int]:
    """Read cost and token totals from a usage report JSON file.

    Returns a dict with cost_usd, input_tokens, and output_tokens keys.
    Returns zeros when the file does not exist or cannot be parsed.
    """
    try:
        with open(report_path, "r") as f:
            report = json.load(f)
        total = report.get("total", {})
        return {
            "cost_usd": float(total.get("cost_usd", 0.0)),
            "input_tokens": int(total.get("input_tokens", 0)),
            "output_tokens": int(total.get("output_tokens", 0)),
        }
    except (IOError, json.JSONDecodeError, TypeError, ValueError):
        return {"cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0}


def _spawn_orchestrator(plan_path: str) -> tuple[int, str, str]:
    """Spawn plan-orchestrator.py and return (exit_code, stdout, stderr).

    Removes CLAUDECODE from the environment so Claude can be spawned
    from within a Claude Code session.
    """
    child_env = os.environ.copy()
    child_env["PYTHONUNBUFFERED"] = "1"
    child_env.pop("CLAUDECODE", None)

    cmd = [PYTHON_BINARY, PLAN_ORCHESTRATOR_SCRIPT, "--plan", plan_path]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=None,  # The orchestrator manages its own task timeouts.
            env=child_env,
            cwd=os.getcwd(),
        )
        return result.returncode, result.stdout or "", result.stderr or ""
    except (OSError, subprocess.SubprocessError) as exc:
        return -1, "", str(exc)


# ─── Node ─────────────────────────────────────────────────────────────────────


def execute_plan(state: PipelineState) -> dict:
    """LangGraph node: execute a YAML plan via plan-orchestrator.py.

    Spawns plan-orchestrator.py as a subprocess, waits for it to complete,
    then reads the usage report JSON to capture cost and token totals.

    Returns partial state updates:
      session_cost_usd: cumulative API-equivalent cost for this plan execution.
      session_input_tokens: cumulative input tokens.
      session_output_tokens: cumulative output tokens.
      rate_limited / rate_limit_reset: set when Claude reports a rate limit.
    """
    plan_path: Optional[str] = state.get("plan_path")
    item_slug: str = state.get("item_slug", "")

    if not plan_path:
        print(f"[execute_plan] No plan_path in state for {item_slug}; skipping.")
        return {}

    print(f"[execute_plan] Executing plan: {plan_path}")
    exit_code, stdout, stderr = _spawn_orchestrator(plan_path)

    combined_output = stdout + stderr
    is_rate_limited, reset_time = check_rate_limit(combined_output)
    if is_rate_limited:
        reset_iso = reset_time.isoformat() if reset_time else None
        print(f"[execute_plan] Rate limited during plan execution for {item_slug}")
        return {
            "rate_limited": True,
            "rate_limit_reset": reset_iso,
        }

    if exit_code != 0:
        print(f"[execute_plan] Orchestrator failed (exit {exit_code}) for {item_slug}")

    report_path = _usage_report_path(plan_path)
    usage = _read_usage_report(report_path)

    return {
        "session_cost_usd": usage["cost_usd"],
        "session_input_tokens": usage["input_tokens"],
        "session_output_tokens": usage["output_tokens"],
    }
