# langgraph_pipeline/pipeline/nodes/plan_creation.py
# create_plan LangGraph node: spawns Claude planner to create YAML plan and design doc.
# Design: docs/plans/2026-02-26-04-pipeline-graph-nodes-design.md

"""create_plan node for the pipeline StateGraph.

Spawns Claude with the 'planner' permission profile to read a backlog item,
produce a design document at docs/plans/{date}-{slug}-design.md, and write
a YAML plan at .claude/plans/{slug}.yaml.

Short-circuits when plan_path is already set (in-progress plan resumption from
a previous pipeline run). Otherwise, runs the plan creation prompt and verifies
the YAML plan was written before returning the paths.
"""

import json
import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

from langgraph_pipeline.pipeline.state import PipelineState
from langgraph_pipeline.shared.config import DEFAULT_AGENTS_DIR, load_orchestrator_config
from langgraph_pipeline.shared.langsmith import add_trace_metadata
from langgraph_pipeline.shared.paths import PLANS_DIR
from langgraph_pipeline.shared.quota import detect_quota_exhaustion
from langgraph_pipeline.shared.rate_limit import check_rate_limit

# ─── Constants ────────────────────────────────────────────────────────────────

CLAUDE_BINARY = "claude"
DESIGN_DIR = "docs/plans"
DESIGN_DOC_DATE_FORMAT = "%Y-%m-%d"
PLAN_CREATION_TIMEOUT_SECONDS = 600
PLANNER_MODEL = "claude-opus-4-6"  # Design and planning require Opus for quality
MAX_DESIGN_VALIDATION_RETRIES = 2  # Max times to retry planner after design validation failure

# Planner permission profile: reads, greps, globes, writes files, and runs shell commands.
PLANNER_ALLOWED_TOOLS = ["Read", "Grep", "Glob", "Write", "Bash"]

# ─── Prompt template ─────────────────────────────────────────────────────────

PLAN_CREATION_PROMPT = (
    "You are creating an implementation plan for a backlog item.\n\n"
    "## Instructions\n\n"
    "1. Read the backlog item file: {item_path}\n"
    "2. Read procedure-coding-rules.md for coding standards\n"
    "3. Read an existing YAML plan for format reference: look at .claude/plans/*.yaml files\n"
    "4. Read the CLAUDE.md file for project conventions\n"
    "5. If the backlog item has a ## Verification Log section, READ IT CAREFULLY.\n"
    "   Previous fix attempts and their verification results are recorded there.\n"
    "   Your plan MUST address any unresolved findings from prior verifications.\n\n"
    "## What to produce\n\n"
    "1. Create a design document at: docs/plans/{date}-{slug}-design.md\n"
    "   - Brief architecture overview\n"
    "   - Key files to create/modify\n"
    "   - Design decisions\n\n"
    "2. Create a YAML plan at: .claude/plans/{slug}.yaml\n"
    "   - Use the exact format: meta + sections with nested tasks\n"
    "   - Each section has: id, name, status: pending, tasks: [...]\n"
    "   - Each task has: id, name, description, status: pending\n"
    "   - The task description should reference the work item file path -- agents read it directly\n"
    "   - Do NOT rewrite or summarize the work item requirements into the task description\n"
    "   - Do NOT add separate verification, review, or code-review tasks\n"
    "   - The orchestrator runs a validator automatically after each task\n\n"
    "3. Validate the plan: python scripts/plan-orchestrator.py --plan .claude/plans/{slug}.yaml --dry-run\n"
    "   - If validation fails, fix the YAML format and retry\n\n"
    "4. Git commit both files with message: \"plan: add {slug} design and YAML plan\"\n\n"
    "## Backlog item type: {item_type}\n\n"
    "## Agent Selection\n\n"
    "Tasks can specify which agent should execute them via the optional \"agent\" field.\n"
    "Available agents are in {agents_dir}:\n\n"
    "- **coder**: Implementation specialist for coding and modification tasks.\n"
    "- **frontend-coder**: Frontend specialist for UI components, pages, and forms.\n"
    "- **e2e-test-agent**: E2E test specialist for Playwright tests (.spec.ts files).\n"
    "- **code-reviewer**: Read-only reviewer for verification and compliance tasks.\n"
    "- **systems-designer**: Architecture and data model designer (read-only).\n"
    "- **planner**: Design-to-implementation bridge. Sets plan_modified: true.\n\n"
    "## Validation\n\n"
    "Plans MUST enable per-task validation and include the source work item path.\n\n"
    "  meta:\n"
    "    source_item: \"{item_path}\"\n"
    "    validation:\n"
    "      enabled: true\n"
    "      run_after:\n"
    "        - coder\n"
    "        - e2e-test-agent\n"
    "        - frontend-coder\n"
    "      validators:\n"
    "        - validator\n"
    "      max_validation_attempts: 2\n\n"
    "Task descriptions reference the work item -- do NOT rewrite requirements:\n\n"
    "  - id: '1.1'\n"
    "    name: Implement work item\n"
    "    agent: coder\n"
    "    description: \"Implement the work item: {item_path}\"\n\n"
    "Do NOT add code-reviewer or verification tasks -- validation handles that.\n\n"
    "## Important\n"
    "- Always set meta.source_item to the backlog file path\n"
    "- Task descriptions reference the work item file, not rewrite it\n"
    "- Keep tasks focused - each task should be completable in one Claude session\n"
)

# ─── Helpers ──────────────────────────────────────────────────────────────────


def _build_planner_command(prompt: str) -> list[str]:
    """Build the Claude CLI command for plan creation with planner permissions.

    Uses --allowedTools with the planner profile when sandbox is enabled,
    otherwise falls back to --dangerously-skip-permissions.
    """
    sandbox_enabled = (
        os.environ.get("ORCHESTRATOR_SANDBOX_ENABLED", "true").lower() != "false"
    )
    cmd = [CLAUDE_BINARY]
    cmd += ["--dangerously-skip-permissions"]
    cmd += ["--permission-mode", "acceptEdits"]
    if sandbox_enabled:
        cmd += ["--allowedTools"] + PLANNER_ALLOWED_TOOLS
        cmd += ["--add-dir", os.getcwd()]
    cmd += ["--model", PLANNER_MODEL]
    cmd += ["--output-format", "json"]
    cmd += ["--print", prompt]
    return cmd


def _run_subprocess(cmd: list[str]) -> tuple[int, str, str]:
    """Spawn the command and return (exit_code, stdout, stderr).

    Removes CLAUDECODE from the environment so Claude can be spawned
    from within a Claude Code session.
    """
    child_env = os.environ.copy()
    child_env["PYTHONUNBUFFERED"] = "1"
    child_env.pop("CLAUDECODE", None)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=PLAN_CREATION_TIMEOUT_SECONDS,
            env=child_env,
            cwd=os.getcwd(),
        )
        return result.returncode, result.stdout or "", result.stderr or ""
    except subprocess.TimeoutExpired:
        return -1, "", "Plan creation subprocess timed out"
    except (OSError, subprocess.SubprocessError) as exc:
        return -1, "", str(exc)


def _extract_cost_from_json_output(stdout: str) -> float:
    """Extract total_cost_usd from Claude CLI JSON output. Returns 0.0 on parse failure."""
    try:
        data = json.loads(stdout)
        return float(data.get("total_cost_usd", 0.0))
    except (json.JSONDecodeError, ValueError, TypeError):
        return 0.0


def _plan_exists(plan_path: str) -> bool:
    """Return True if the YAML plan file exists and is non-empty."""
    path = Path(plan_path)
    return path.exists() and path.stat().st_size > 0


def _ensure_acceptance_criteria_in_design(
    item_path: str, design_doc_path: str, item_slug: str
) -> None:
    """Copy acceptance criteria from the backlog item into the design doc if missing.

    Reads the backlog item, extracts the '## Acceptance Criteria' section, and
    appends it to the design doc if the design doc doesn't already contain one.
    """
    design_path = Path(design_doc_path)
    if not design_path.exists():
        return
    try:
        item_text = Path(item_path).read_text(encoding="utf-8")
        design_text = design_path.read_text(encoding="utf-8")
    except OSError:
        return

    # Already has criteria
    if "## Acceptance Criteria" in design_text:
        return

    # Extract from backlog item
    marker = "## Acceptance Criteria"
    idx = item_text.find(marker)
    if idx < 0:
        logger.info("No acceptance criteria in backlog item for %s — skipping", item_slug)
        return

    # Find the end: next ## heading or end of file
    rest = item_text[idx + len(marker):]
    next_heading = rest.find("\n## ")
    if next_heading >= 0:
        criteria_text = marker + rest[:next_heading].rstrip()
    else:
        criteria_text = marker + rest.rstrip()

    try:
        with open(design_doc_path, "a", encoding="utf-8") as f:
            f.write(f"\n\n{criteria_text}\n")
        logger.info("Copied acceptance criteria into design doc for %s", item_slug)
    except OSError as exc:
        logger.warning("Failed to append criteria to design doc for %s: %s", item_slug, exc)


# ─── Node ─────────────────────────────────────────────────────────────────────


def create_plan(state: PipelineState) -> dict:
    """LangGraph node: spawn Claude to create a design doc and YAML plan.

    Short-circuits when plan_path is already set (in-progress plan resumption).
    Otherwise, builds the plan creation prompt, spawns Claude with planner
    permissions, and verifies the YAML plan was written to disk.

    Returns partial state updates:
      plan_path: path to .claude/plans/{slug}.yaml on success.
      design_doc_path: expected docs/plans/{date}-{slug}-design.md path.
      rate_limited / rate_limit_reset: set when Claude reports a rate limit.
    """
    item_path: str = state.get("item_path", "")
    item_slug: str = state.get("item_slug", "")
    item_type: str = state.get("item_type", "feature")
    plan_path: Optional[str] = state.get("plan_path")

    # Short-circuit: plan already exists (in-progress plan resumption).
    if plan_path and _plan_exists(plan_path):
        return {}

    config = load_orchestrator_config()
    agents_dir = config.get("agents_dir", DEFAULT_AGENTS_DIR)
    date_str = datetime.now().strftime(DESIGN_DOC_DATE_FORMAT)

    expected_plan_path = f"{PLANS_DIR}/{item_slug}.yaml"
    expected_design_doc_path = f"{DESIGN_DIR}/{date_str}-{item_slug}-design.md"

    prompt = PLAN_CREATION_PROMPT.format(
        item_path=item_path,
        date=date_str,
        slug=item_slug,
        item_type=item_type,
        agents_dir=agents_dir,
    )

    cmd = _build_planner_command(prompt)
    exit_code, stdout, stderr = _run_subprocess(cmd)
    total_cost_usd = _extract_cost_from_json_output(stdout)

    # Only check stderr for rate limit / quota signals — stdout contains
    # Claude's response which may include those keywords literally (e.g.
    # when the work item discusses rate limit handling).
    if exit_code != 0:
        is_rate_limited, reset_time = check_rate_limit(stderr)
        if is_rate_limited and reset_time is not None:
            logger.warning("Rate limited during plan creation for %s", item_slug)
            return {
                "rate_limited": True,
                "rate_limit_reset": reset_time.isoformat(),
            }

        if detect_quota_exhaustion(stderr):
            logger.warning("Quota exhausted during plan creation for %s", item_slug)
            return {"quota_exhausted": True}

        logger.warning(
            "Plan creation failed for %s (exit %d): stderr=%s",
            item_slug, exit_code, stderr[:500],
        )
        return {}

    if not _plan_exists(expected_plan_path):
        # Log what the planner DID produce to help diagnose
        logger.warning(
            "Plan YAML not created at %s. exit_code=%d cost=$%.4f stdout_len=%d stderr_len=%d",
            expected_plan_path, exit_code, total_cost_usd, len(stdout), len(stderr),
        )
        if stderr:
            logger.warning("Planner stderr: %s", stderr[:500])
        # Check if planner wrote it to a different path
        plan_dir = Path(PLANS_DIR)
        yamls = list(plan_dir.glob(f"*{item_slug}*.yaml"))
        if yamls:
            logger.warning("Found YAML at unexpected path: %s", yamls)
        return {}

    logger.info("Plan created: %s", expected_plan_path)

    # Ensure acceptance criteria from the backlog item are in the design doc.
    # The planner often omits them, so we copy them directly rather than retrying.
    _ensure_acceptance_criteria_in_design(item_path, expected_design_doc_path, item_slug)

    # Validate design quality with Opus.
    if Path(expected_design_doc_path).exists():
        logger.info("Running design validation for %s...", item_slug)
        from langgraph_pipeline.pipeline.nodes.intake import _validate_design
        valid, reason = _validate_design(expected_design_doc_path, item_path)
        if valid:
            logger.info("Design validation PASSED for %s", item_slug)
        else:
            logger.warning("Design validation FAILED for %s: %s", item_slug, reason)
    else:
        logger.warning("No design doc at %s — skipping validation", expected_design_doc_path)

    add_trace_metadata({
        "node_name": "create_plan",
        "graph_level": "pipeline",
        "item_slug": item_slug,
        "item_type": item_type,
        "total_cost_usd": total_cost_usd,
        "tags": [item_slug, item_type],
    })
    return {
        "plan_path": expected_plan_path,
        "design_doc_path": expected_design_doc_path,
    }
