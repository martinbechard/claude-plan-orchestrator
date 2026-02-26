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
from typing import Optional

import yaml

from langgraph_pipeline.executor.state import TaskState, ValidationVerdict
from langgraph_pipeline.shared.claude_cli import (
    OutputCollector,
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

# Maps ModelTier literals to full Claude CLI model identifiers
MODEL_TIER_TO_CLI_NAME: dict[str, str] = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-6",
}

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
        '  "message": "Brief summary of findings"\n'
        "}\n"
        "```\n\n"
        "IMPORTANT: You MUST write the status file before finishing.\n"
    )


# ─── Claude CLI Execution ─────────────────────────────────────────────────────


def _build_child_env() -> dict:
    """Return environment dict with CLAUDECODE stripped for child Claude processes."""
    env = os.environ.copy()
    env.pop(STRIPPED_ENV_VAR, None)
    return env


def _run_claude(prompt: str, model_cli_name: str) -> tuple[bool, dict]:
    """Spawn Claude CLI and stream its output. Returns (success, result_capture)."""
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
            args=(process.stdout, stdout_collector, result_capture),
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

        return (process.returncode == 0, result_capture)

    except subprocess.TimeoutExpired:
        print(f"[validate_task] Claude CLI timed out after {CLAUDE_TIMEOUT_SECONDS}s")
        return (False, {})
    except Exception as exc:
        print(f"[validate_task] Failed to spawn Claude CLI: {exc}")
        return (False, {})


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
    effective_model: str = state.get("effective_model") or "sonnet"

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
            f"for task {task_id!r}; treating as PASS"
        )
        _save_plan_yaml(plan_path, plan_data)
        return {"last_validation_verdict": "PASS", "plan_data": plan_data}

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
    cli_success, result_capture = _run_claude(full_prompt, model_cli_name)

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

    return {
        "last_validation_verdict": verdict,
        "plan_data": plan_data,
        "task_attempt": new_task_attempt,
        "plan_cost_usd": (state.get("plan_cost_usd") or 0.0) + cost_usd,
        "plan_input_tokens": (state.get("plan_input_tokens") or 0) + input_tokens,
        "plan_output_tokens": (state.get("plan_output_tokens") or 0) + output_tokens,
    }
