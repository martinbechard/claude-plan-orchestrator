# langgraph_pipeline/executor/nodes/validator.py
# validate_task LangGraph node: runs post-task validation via Claude CLI.
# Design: docs/plans/2026-02-26-05-task-execution-subgraph-design.md

"""validate_task node for the executor StateGraph.

Runs post-task validation when enabled in plan config. Spawns Claude CLI with
the configured validator agent, parses the PASS/WARN/FAIL verdict from the
written status file, stores findings on the task, and increments task_attempt
on FAIL so the retry_check edge can route back to escalate -> execute_task.
"""

import json
import os
import subprocess
import threading
import time
import urllib.request
from typing import Optional

import yaml

from langgraph_pipeline.executor.state import TaskState, ValidationVerdict
from langgraph_pipeline.shared.langsmith import add_trace_metadata
from langgraph_pipeline.shared.claude_cli import (
    OutputCollector,
    ToolCallRecord,
    stream_json_output,
    stream_output,
)
from langgraph_pipeline.shared.config import load_orchestrator_config
from langgraph_pipeline.shared.paths import STATUS_FILE_PATH

# ─── Constants ────────────────────────────────────────────────────────────────

CLAUDE_TIMEOUT_SECONDS = 900          # 15 minutes per validation run
DEFAULT_AGENTS_DIR = ".claude/agents"
DEFAULT_VALIDATOR_AGENT = "validator"
DEFAULT_BUILD_COMMAND = "pnpm run build"
DEFAULT_TEST_COMMAND = "pnpm test"
STRIPPED_ENV_VAR = "CLAUDECODE"       # removed so Claude can spawn from Claude Code
COST_API_TIMEOUT_S = 10               # timeout for POST /api/cost

# Maps ModelTier literals to full Claude CLI model identifiers
MODEL_TIER_TO_CLI_NAME: dict[str, str] = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-6",
}

# Validators must be at least sonnet — haiku is not reliable enough for judging.
VALIDATOR_MODEL_FLOOR = "sonnet"
MODEL_TIER_ORDER = ("haiku", "sonnet", "opus")

# Task status that qualifies for validation
_TASK_STATUS_COMPLETED = "completed"

# ─── Plan Helpers ─────────────────────────────────────────────────────────────


def _find_task_by_id(plan_data: dict, task_id: str) -> Optional[dict]:
    """Return the task dict with the given id, searching all sections."""
    for section in plan_data.get("sections", []):
        for task in section.get("tasks", []):
            if task.get("id") == task_id:
                return task
    return None


def _save_plan_yaml(plan_path: str, plan_data: dict) -> None:
    """Write the plan dict back to disk in YAML format."""
    with open(plan_path, "w") as f:
        yaml.dump(plan_data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


# ─── Validator Agent Loading ──────────────────────────────────────────────────


def _load_agent_body(agent_name: str, agents_dir: str) -> str:
    """Load the body text of a validator agent definition, stripping YAML frontmatter.

    Returns an empty string if the file is missing or unreadable.
    """
    agent_path = os.path.join(agents_dir, f"{agent_name}.md")
    if not os.path.isfile(agent_path):
        print(f"[validate_task] Validator agent not found: {agent_path}")
        return ""
    try:
        with open(agent_path) as f:
            content = f.read()
        parts = content.split("---", 2)
        if len(parts) >= 3 and not parts[0].strip():
            return parts[2].lstrip("\n")
        return content
    except Exception as exc:
        print(f"[validate_task] Failed to load validator agent {agent_name!r}: {exc}")
        return ""


# ─── Prompt Building ──────────────────────────────────────────────────────────


def _build_validator_prompt(
    plan_data: dict,
    task: dict,
    build_command: str,
    test_command: str,
) -> str:
    """Build the prompt string for the validator agent."""
    work_item = plan_data.get("meta", {}).get("source_item", "")
    plan_doc = plan_data.get("meta", {}).get("plan_doc", "")
    result_message = task.get("result_message", "No result message available")
    return (
        f"Validate task {task['id']} from the implementation plan.\n\n"
        "## Task Details\n"
        f"- **Task ID:** {task['id']}\n"
        f"- **Task Name:** {task.get('name', task['id'])}\n"
        f"- **Description:** {task.get('description', 'No description')}\n"
        f"- **Plan Document:** {plan_doc}\n"
        f"- **Work Item:** {work_item}\n"
        f"- **Result Message:** {result_message}\n\n"
        "## Validation Commands\n"
        f"- **Build Command:** {build_command}\n"
        f"- **Test Command:** {test_command}\n\n"
        "## Status File\n"
        f"Write your verdict to `{STATUS_FILE_PATH}` in this format:\n"
        "```json\n"
        "{\n"
        f'  "task_id": "{task["id"]}",\n'
        '  "verdict": "PASS",\n'
        '  "status": "completed",\n'
        '  "message": "Brief summary of findings",\n'
        '  "requirements_checked": 5,\n'
        '  "requirements_met": 5\n'
        "}\n"
        "```\n\n"
        "The `requirements_checked` and `requirements_met` fields are optional but "
        "recommended when you can count discrete acceptance criteria.\n\n"
        "IMPORTANT: You MUST write the status file before finishing.\n"
    )


# ─── Claude CLI Execution ─────────────────────────────────────────────────────


def _build_child_env() -> dict:
    """Return environment dict with CLAUDECODE stripped for child Claude processes."""
    env = os.environ.copy()
    env.pop(STRIPPED_ENV_VAR, None)
    return env


def _run_claude(prompt: str, model_cli_name: str) -> tuple[bool, int, dict, str, list[ToolCallRecord]]:
    """Spawn Claude CLI and stream its output.

    Returns (success, returncode, result_capture, stderr_text, tool_calls).
    success is True when Claude exits with return code 0.
    returncode is process.returncode on normal exit, -1 on TimeoutExpired, -2 on Exception.
    result_capture holds the parsed 'result' JSON event with usage data.
    tool_calls accumulates ToolCallRecord entries from each tool_use event.
    """
    cmd = [
        "claude",
        "--dangerously-skip-permissions",
        "--output-format", "stream-json",
        "--verbose",
        "--model", model_cli_name,
        "--print", prompt,
    ]
    stdout_collector = OutputCollector()
    stderr_collector = OutputCollector()
    result_capture: dict = {}
    tool_calls: list[ToolCallRecord] = []

    start_time = time.time()
    try:
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=os.getcwd(),
            env=_build_child_env(),
        )
        stdout_thread = threading.Thread(
            target=stream_json_output,
            args=(process.stdout, stdout_collector, result_capture, tool_calls),
        )
        stderr_thread = threading.Thread(
            target=stream_output,
            args=(process.stderr, "ERR", stderr_collector, True),
        )
        stdout_thread.start()
        stderr_thread.start()

        while process.poll() is None:
            time.sleep(1)
            if time.time() - start_time > CLAUDE_TIMEOUT_SECONDS:
                process.terminate()
                process.wait(timeout=5)
                raise subprocess.TimeoutExpired(cmd, CLAUDE_TIMEOUT_SECONDS)

        stdout_thread.join(timeout=5)
        stderr_thread.join(timeout=5)

        return (process.returncode == 0, process.returncode, result_capture, stderr_collector.get_output(), tool_calls)

    except subprocess.TimeoutExpired:
        print(f"[validate_task] Claude CLI timed out after {CLAUDE_TIMEOUT_SECONDS}s")
        return (False, -1, {}, "Timed out", [])
    except Exception as exc:
        print(f"[validate_task] Failed to spawn Claude CLI: {exc}")
        return (False, -2, {}, str(exc), [])


# ─── Cost Reporting ───────────────────────────────────────────────────────────


import logging

_logger = logging.getLogger(__name__)


def _tool_call_to_dict(tc: ToolCallRecord) -> dict:
    """Convert a ToolCallRecord to a ToolCallEntry dict for the cost API."""
    tool_name = tc["tool_name"]
    tool_input = tc.get("tool_input") or {}
    file_path: Optional[str] = None
    command: Optional[str] = None
    if tool_name in ("Read", "Edit", "Write"):
        file_path = tool_input.get("file_path")
    elif tool_name in ("Grep", "Glob"):
        file_path = tool_input.get("path")
    elif tool_name == "Bash":
        command = tool_input.get("command")
    entry: dict = {"tool": tool_name}
    if file_path is not None:
        entry["file_path"] = file_path
    if command is not None:
        entry["command"] = command
    result_bytes = tc.get("result_bytes")
    if result_bytes is not None:
        entry["result_bytes"] = result_bytes
    return entry


def _post_cost_to_api(
    plan_data: dict,
    task_id: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    duration_s: float,
    tool_calls: list[ToolCallRecord],
) -> None:
    """POST a validator cost record to {LANGCHAIN_ENDPOINT}/api/cost.

    Only posts when LANGCHAIN_ENDPOINT is set to a localhost URL.
    Fire-and-forget: logs a warning on error but never raises.
    """
    from pathlib import Path as _Path
    endpoint = os.environ.get("LANGCHAIN_ENDPOINT", "")
    if not endpoint.startswith("http://localhost"):
        return

    source_item = plan_data.get("meta", {}).get("source_item", "")
    item_slug = _Path(source_item).stem if source_item else ""
    item_type = "defect" if source_item and "defect" in source_item.lower() else "feature"

    tool_call_dicts = [
        _tool_call_to_dict(tc)
        for tc in tool_calls
        if tc.get("type") == "tool_use"
    ]

    payload = {
        "item_slug": item_slug,
        "item_type": item_type,
        "task_id": task_id,
        "agent_type": "validator",
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost_usd,
        "duration_s": round(duration_s, 1),
        "tool_calls": tool_call_dicts,
    }

    url = f"{endpoint}/api/cost"
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=COST_API_TIMEOUT_S):
            pass
    except Exception as exc:
        _logger.warning("[validate_task] Failed to POST cost to %s: %s", url, exc)


# ─── Status File ──────────────────────────────────────────────────────────────


def _clear_status_file() -> None:
    """Remove the status file so stale task_runner output cannot pollute verdict parsing."""
    try:
        if os.path.exists(STATUS_FILE_PATH):
            os.remove(STATUS_FILE_PATH)
    except OSError as exc:
        print(f"[validate_task] Could not clear status file: {exc}")


def _read_status_file() -> Optional[dict]:
    """Read and parse the task-status.json written by the validator agent."""
    if not os.path.exists(STATUS_FILE_PATH):
        return None
    try:
        with open(STATUS_FILE_PATH) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


# ─── Verdict Parsing ──────────────────────────────────────────────────────────


def _parse_verdict(status_dict: Optional[dict], cli_success: bool) -> ValidationVerdict:
    """Extract a PASS/WARN/FAIL verdict from the validator's status file.

    Priority:
    1. Explicit 'verdict' field containing PASS, WARN, or FAIL.
    2. Keywords in the 'message' field (PASS or WARN only if FAIL absent).
    3. CLI success + status==completed -> PASS fallback.
    4. FAIL when no file was written or nothing matched.
    """
    if status_dict is None:
        return "FAIL"

    explicit = str(status_dict.get("verdict", "")).upper()
    if explicit in ("PASS", "WARN", "FAIL"):
        return explicit  # type: ignore[return-value]

    message_upper = str(status_dict.get("message", "")).upper()
    if "FAIL" in message_upper:
        return "FAIL"
    if "WARN" in message_upper:
        return "WARN"
    if "PASS" in message_upper:
        return "PASS"

    if cli_success and status_dict.get("status") == _TASK_STATUS_COMPLETED:
        return "PASS"

    return "FAIL"


# ─── Node ─────────────────────────────────────────────────────────────────────


def validate_task(state: TaskState) -> dict:
    """LangGraph node: validate a completed task via the configured validator agent.

    Sequence:
    1. Skip validation when disabled, task not found, task not completed, agent
       not in run_after list, or max_validation_attempts exceeded.
    2. Clear the status file so stale task_runner output cannot pollute verdict.
    3. Build a prompt and spawn Claude CLI with the validator agent.
    4. Parse the PASS/WARN/FAIL verdict from the written status file.
    5. On FAIL: store validation_findings on the task dict and increment task_attempt.
    6. Persist the plan YAML and return updated state.

    Returns a partial state dict with last_validation_verdict, plan_data,
    task_attempt, and updated cost accumulators.
    """
    task_id = state.get("current_task_id")
    if task_id is None:
        print("[validate_task] No current_task_id; skipping validation")
        return {"last_validation_verdict": "PASS"}

    plan_data: dict = state.get("plan_data") or {}
    plan_path: str = state["plan_path"]
    task_attempt: int = state.get("task_attempt") or 1
    task_model: str = state.get("effective_model") or "sonnet"
    # Enforce sonnet as the minimum model for validation — haiku is not reliable as a judge.
    effective_model = (
        task_model
        if MODEL_TIER_ORDER.index(task_model) >= MODEL_TIER_ORDER.index(VALIDATOR_MODEL_FLOOR)
        else VALIDATOR_MODEL_FLOOR
    )

    validation_config = plan_data.get("meta", {}).get("validation", {})
    if not validation_config.get("enabled", False):
        print(f"[validate_task] Validation disabled; skipping task {task_id!r}")
        return {"last_validation_verdict": "PASS"}

    task = _find_task_by_id(plan_data, task_id)
    if task is None:
        print(f"[validate_task] Task {task_id!r} not found in plan_data; skipping")
        return {"last_validation_verdict": "PASS"}

    if task.get("status") != _TASK_STATUS_COMPLETED:
        print(f"[validate_task] Task {task_id!r} status {task.get('status')!r} is not completed; skipping")
        return {"last_validation_verdict": "PASS"}

    run_after = validation_config.get("run_after", [])
    agent_name = task.get("agent", "coder")
    if run_after and agent_name not in run_after:
        print(f"[validate_task] Agent {agent_name!r} not in run_after; skipping task {task_id!r}")
        return {"last_validation_verdict": "PASS"}

    max_validation_attempts = int(validation_config.get("max_validation_attempts", 2))
    validation_attempts = (task.get("validation_attempts") or 0) + 1
    task["validation_attempts"] = validation_attempts

    if validation_attempts > max_validation_attempts:
        print(
            f"[validate_task] Max validation attempts ({max_validation_attempts}) reached "
            f"for task {task_id!r}; treating as WARN"
        )
        _save_plan_yaml(plan_path, plan_data)
        return {"last_validation_verdict": "WARN", "plan_data": plan_data}

    validators = validation_config.get("validators", [DEFAULT_VALIDATOR_AGENT])
    validator_agent = validators[0] if validators else DEFAULT_VALIDATOR_AGENT

    config = load_orchestrator_config()
    agents_dir = config.get("agents_dir", DEFAULT_AGENTS_DIR)
    build_command = config.get("build_command", DEFAULT_BUILD_COMMAND)
    test_command = config.get("test_command", DEFAULT_TEST_COMMAND)

    agent_body = _load_agent_body(validator_agent, agents_dir)
    task_prompt = _build_validator_prompt(plan_data, task, build_command, test_command)
    full_prompt = (agent_body + "\n\n---\n\n" + task_prompt) if agent_body else task_prompt

    model_cli_name = MODEL_TIER_TO_CLI_NAME.get(effective_model, effective_model)
    print(f"[validate_task] Running validator {validator_agent!r} for task {task_id!r}")

    _clear_status_file()
    _exec_start = time.time()
    cli_success, returncode, result_capture, stderr_text, tool_calls = _run_claude(full_prompt, model_cli_name)
    _duration_ms = int((time.time() - _exec_start) * 1000)

    if returncode == 0:
        failure_reason = "ok"
    elif returncode == -1:
        failure_reason = "timeout"
    else:
        failure_reason = f"exit_code_{returncode}"

    status_dict = _read_status_file()
    verdict = _parse_verdict(status_dict, cli_success)

    print(f"[validate_task] Verdict for task {task_id!r}: {verdict}")

    if status_dict is not None:
        task["validation_findings"] = status_dict.get("message", "")
    else:
        task["validation_findings"] = (
            f"Validator {validator_agent!r} failed to execute: No status file written by Claude"
        )

    new_task_attempt = task_attempt + 1 if verdict == "FAIL" else task_attempt
    _save_plan_yaml(plan_path, plan_data)

    cost_usd = float(result_capture.get("total_cost_usd", 0.0))
    usage = result_capture.get("usage", {})
    input_tokens = int(usage.get("input_tokens", 0))
    output_tokens = int(usage.get("output_tokens", 0))

    # Post cost record to the web API (fire-and-forget)
    _post_cost_to_api(
        plan_data=plan_data,
        task_id=task_id,
        model=model_cli_name,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        duration_s=_duration_ms / 1000.0,
        tool_calls=tool_calls,
    )

    add_trace_metadata({
        "node_name": "validate_task",
        "graph_level": "executor",
        "task_id": task_id,
        "model": effective_model,
        "total_cost_usd": cost_usd,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "duration_ms": _duration_ms,
        "verdict": verdict,
        "subprocess_exit_code": returncode,
        "subprocess_error": stderr_text[:500] if not cli_success else "",
        "failure_reason": failure_reason,
        "findings": task.get("validation_findings", ""),
        "requirements_checked": status_dict.get("requirements_checked") if status_dict else None,
        "requirements_met": status_dict.get("requirements_met") if status_dict else None,
    })

    return {
        "last_validation_verdict": verdict,
        "plan_data": plan_data,
        "task_attempt": new_task_attempt,
        "plan_cost_usd": (state.get("plan_cost_usd") or 0.0) + cost_usd,
        "plan_input_tokens": (state.get("plan_input_tokens") or 0) + input_tokens,
        "plan_output_tokens": (state.get("plan_output_tokens") or 0) + output_tokens,
    }
