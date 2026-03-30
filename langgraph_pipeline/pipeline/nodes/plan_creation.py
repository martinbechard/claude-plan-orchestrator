# langgraph_pipeline/pipeline/nodes/plan_creation.py
# create_plan LangGraph node: spawns Claude planner to create YAML plan and design doc.
# Design: docs/plans/2026-02-26-04-pipeline-graph-nodes-design.md

"""create_plan node for the pipeline StateGraph.

Spawns Claude with the 'planner' permission profile to read a backlog item,
produce a design document at docs/plans/{date}-{slug}-design.md, and write
a YAML plan at tmp/plans/{slug}.yaml.

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
    "2. Read the structured requirements file: {requirements_path}\n"
    "   This file contains numbered requirements (P1, P2, ...) with type tags,\n"
    "   acceptance criteria, and a coverage matrix. Use these as the basis for\n"
    "   your plan — they are the validated, structured version of the raw request.\n"
    "3. Read procedure-coding-rules.md for coding standards\n"
    "4. Read an existing YAML plan for format reference: look at tmp/plans/*.yaml files\n"
    "5. Read the CLAUDE.md file for project conventions\n"
    "6. If the backlog item has a ## Verification Log section, READ IT CAREFULLY.\n"
    "   Previous fix attempts and their verification results are recorded there.\n"
    "   Your plan MUST address any unresolved findings from prior verifications.\n\n"
    "## What to produce\n\n"
    "1. Create a design document at: docs/plans/{date}-{slug}-design.md\n"
    "   - Brief architecture overview\n"
    "   - Key files to create/modify\n"
    "   - Numbered design decisions (D1, D2, ...) where each D<n> declares:\n"
    "     - Addresses: which P<n>/UC<n>/FR<n> requirements it covers\n"
    "     - Satisfies: which AC<n> acceptance criteria it contributes to\n"
    "     - Approach: how the design decision will be implemented\n"
    "     - Files: which files will be created or modified\n"
    "   - A Design -> AC traceability grid at the end showing:\n"
    "     | AC | Design Decision(s) | Approach |\n\n"
    "2. Create a YAML plan at: tmp/plans/{slug}.yaml\n"
    "   - Use the exact format: meta + sections with nested tasks\n"
    "   - Each section has: id, name, status: pending, tasks: [...]\n"
    "   - Each task has: id, name, description, status: pending\n"
    "   - Each task SHOULD include a target_acs field listing which AC<n> it addresses\n"
    "   - The task description should reference the work item file path -- agents read it directly\n"
    "   - Each task description MUST note which P<n> requirement(s) and D<n> design decision(s) it implements\n"
    "   - Do NOT rewrite or summarize the work item requirements into the task description\n"
    "   - Do NOT add separate verification, review, or code-review tasks\n"
    "   - The orchestrator runs a validator automatically after each task\n\n"
    "3. Validate the plan: python scripts/plan-orchestrator.py --plan tmp/plans/{slug}.yaml --dry-run\n"
    "   - If validation fails, fix the YAML format and retry\n\n"
    "4. Git commit both files with message: \"plan: add {slug} design and YAML plan\"\n\n"
    "## Backlog item type: {item_type}\n\n"
    "## Requirement-Driven Agent Routing\n\n"
    "Analyze each requirement's type tag from the structured requirements file and\n"
    "select the appropriate pipeline pattern:\n\n"
    "- Requirements tagged **UI**: Create a Phase 0 design competition section with\n"
    "  3 design approach tasks (agents: systems-designer, ux-designer, or frontend-coder\n"
    "  in the same parallel_group), followed by a design-judge task (depends on all\n"
    "  design tasks), then a planner task to extend with implementation details.\n\n"
    "- Requirements tagged **functional** or **refactoring**: Create implementation\n"
    "  sections with coder agent tasks, followed by automatic validation.\n\n"
    "- Requirements tagged **performance**: Create analysis tasks with systems-designer,\n"
    "  then coder implementation with benchmarks.\n\n"
    "- **Mixed requirement sets**: Combine patterns. Phase 0 for UI portions, then\n"
    "  implementation sections for code portions, with proper depends_on between them.\n\n"
    "## Available Agents\n\n"
    "Tasks specify which agent executes them via the \"agent\" field.\n"
    "{agent_catalog}\n\n"
    "## Validation\n\n"
    "Plans MUST enable per-task validation and include the source work item path.\n\n"
    "  meta:\n"
    "    source_item: \"{item_path}\"\n"
    "    requirements_path: \"{requirements_path}\"\n"
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
    "    name: Implement P1 and P2\n"
    "    agent: coder\n"
    "    description: \"Implement requirements P1, P2 from work item: {item_path}\"\n\n"
    "Do NOT add code-reviewer or verification tasks -- validation handles that.\n\n"
    "## Important\n"
    "- Always set meta.source_item to the backlog file path\n"
    "- Always set meta.requirements_path to the structured requirements file path\n"
    "- Task descriptions reference the work item file AND which P<n> requirements they address\n"
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



def _build_agent_catalog(agents_dir: str) -> str:
    """Build a formatted catalog of available agents from their definition files.

    Reads each .md file in agents_dir, extracts the YAML frontmatter (name,
    description, model), and returns a formatted string listing all agents.
    """
    agents_path = Path(agents_dir)
    if not agents_path.exists():
        return "Agent definitions directory not found."

    catalog_lines: list[str] = []
    for agent_file in sorted(agents_path.glob("*.md")):
        try:
            content = agent_file.read_text(encoding="utf-8")
            # Extract YAML frontmatter between --- markers
            if content.startswith("---"):
                end_idx = content.index("---", 3)
                frontmatter = content[3:end_idx].strip()
                name = ""
                description = ""
                model = ""
                for line in frontmatter.split("\n"):
                    line = line.strip()
                    if line.startswith("name:"):
                        name = line[5:].strip().strip('"')
                    elif line.startswith("description:"):
                        # Handle multi-line descriptions
                        description = line[12:].strip().strip('"')
                    elif line.startswith("model:"):
                        model = line[6:].strip()
                if name:
                    catalog_lines.append(f"- **{name}** (model: {model}): {description}")
        except (OSError, ValueError):
            continue

    if not catalog_lines:
        return "No agent definitions found."
    return "\n".join(catalog_lines)


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


DESIGN_VALIDATION_MODEL = "claude-haiku-4-5-20251001"


def _run_design_skill_validation(
    skill_name: str,
    input_artifacts: dict[str, str],
    output_artifact: str,
    slug: str,
    step_number: int,
    step_name: str,
) -> tuple[bool, float]:
    """Run skill-based cross-reference validation for design/plan steps.

    Returns (valid, cost). Non-blocking: logs warnings on failure.
    """
    from langgraph_pipeline.shared.claude_cli import call_claude
    from langgraph_pipeline.shared.traceability import load_validation_skill, save_cross_reference_report

    try:
        skill_content = load_validation_skill(skill_name)
    except FileNotFoundError:
        logger.warning("Validation skill not found: %s — skipping", skill_name)
        return True, 0.0

    inputs_section = "\n\n".join(
        f"## {name}\n\n---\n{content}\n---"
        for name, content in input_artifacts.items()
    )
    prompt = (
        f"You are a validation agent. Follow the cross-reference procedure and "
        f"quality gates in the skill below to validate the output artifact.\n\n"
        f"## Validation Skill\n\n{skill_content}\n\n"
        f"## Input Artifacts\n\n{inputs_section}\n\n"
        f"## Output Artifact to Validate\n\n---\n{output_artifact}\n---\n\n"
        f"Produce the cross-reference report in the format specified by the skill. "
        f"At the end, state the verdict: PASS, WARN, or FAIL."
    )
    result = call_claude(prompt, model=DESIGN_VALIDATION_MODEL)
    cost = result.total_cost_usd

    if result.failure_reason:
        logger.warning("Step %d validation failed for %s: %s", step_number, slug, result.failure_reason)
        return False, cost

    output = result.text
    try:
        save_cross_reference_report(slug, step_number, step_name, output)
    except OSError as exc:
        logger.warning("Failed to save cross-reference report: %s", exc)

    upper_lines = output.strip().upper().split("\n")
    last_line = upper_lines[-1] if upper_lines else ""
    if "FAIL" in last_line:
        logger.warning("Step %d validation FAIL for %s", step_number, slug)
        return False, cost
    if "WARN" in last_line:
        logger.info("Step %d validation WARN for %s", step_number, slug)
    else:
        logger.info("Step %d validation PASS for %s", step_number, slug)
    return True, cost


# ─── Node ─────────────────────────────────────────────────────────────────────


def create_plan(state: PipelineState) -> dict:
    """LangGraph node: spawn Claude to create a design doc and YAML plan.

    Short-circuits when plan_path is already set (in-progress plan resumption).
    Otherwise, builds the plan creation prompt, spawns Claude with planner
    permissions, and verifies the YAML plan was written to disk.

    Returns partial state updates:
      plan_path: path to tmp/plans/{slug}.yaml on success.
      design_doc_path: expected docs/plans/{date}-{slug}-design.md path.
      rate_limited / rate_limit_reset: set when Claude reports a rate limit.
    """
    item_path: str = state.get("item_path", "")
    item_slug: str = state.get("item_slug", "")
    item_type: str = state.get("item_type", "feature")
    plan_path: Optional[str] = state.get("plan_path")
    requirements_path: str = state.get("requirements_path", "")

    # Short-circuit: plan already exists (in-progress plan resumption).
    if plan_path and _plan_exists(plan_path):
        return {}

    config = load_orchestrator_config()
    agents_dir = config.get("agents_dir", DEFAULT_AGENTS_DIR)
    date_str = datetime.now().strftime(DESIGN_DOC_DATE_FORMAT)

    expected_plan_path = f"{PLANS_DIR}/{item_slug}.yaml"
    expected_design_doc_path = f"{DESIGN_DIR}/{date_str}-{item_slug}-design.md"

    # Build the agent catalog from agent definition files
    agent_catalog = _build_agent_catalog(agents_dir)

    # Use requirements_path if available, fall back to empty string
    effective_requirements_path = requirements_path or "(no structured requirements available)"

    prompt = PLAN_CREATION_PROMPT.format(
        item_path=item_path,
        requirements_path=effective_requirements_path,
        date=date_str,
        slug=item_slug,
        item_type=item_type,
        agent_catalog=agent_catalog,
    )

    cmd = _build_planner_command(prompt)
    exit_code, stdout, stderr = _run_subprocess(cmd)
    total_cost_usd = _extract_cost_from_json_output(stdout)

    # Save planner output and report tokens to dashboard
    from langgraph_pipeline.pipeline.nodes.intake import _save_subprocess_output
    from langgraph_pipeline.shared.claude_cli import _report_worker_stats
    _save_subprocess_output(item_slug, "planner", stdout, stderr, exit_code)
    try:
        planner_json = json.loads(stdout)
        usage = planner_json.get("usage", {})
        planner_in = int(usage.get("input_tokens", 0))
        planner_out = int(usage.get("output_tokens", 0))
        _report_worker_stats(planner_in, planner_out, total_cost_usd)
    except (json.JSONDecodeError, TypeError):
        pass


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
        # Log permission denials from the JSON output
        try:
            result_json = json.loads(stdout)
            denials = result_json.get("permission_denials", [])
            if denials:
                logger.warning("Planner permission denials: %s", json.dumps(denials, indent=2)[:1000])
            result_text = result_json.get("result", "")
            if result_text:
                logger.warning("Planner result text (last 500 chars): %s", result_text[-500:])
        except (json.JSONDecodeError, TypeError):
            pass
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

    # Validate design and plan with skill-based cross-reference checks.
    design_doc_content = ""
    if Path(expected_design_doc_path).exists():
        try:
            design_doc_content = Path(expected_design_doc_path).read_text(encoding="utf-8")
        except OSError:
            pass

    requirements_content = ""
    if requirements_path:
        try:
            requirements_content = Path(requirements_path).read_text(encoding="utf-8")
        except OSError:
            pass

    if design_doc_content and requirements_content:
        # Step 5: Design validation.
        logger.info("Running design validation (Step 5) for %s...", item_slug)
        design_valid, design_cost = _run_design_skill_validation(
            skill_name="design-validation.md",
            input_artifacts={"Structured Requirements + AC Register": requirements_content},
            output_artifact=design_doc_content,
            slug=item_slug,
            step_number=5,
            step_name="design",
        )
        total_cost_usd += design_cost

        # Step 6: Plan validation.
        if _plan_exists(expected_plan_path):
            try:
                plan_content = Path(expected_plan_path).read_text(encoding="utf-8")
            except OSError:
                plan_content = ""
            if plan_content:
                logger.info("Running plan validation (Step 6) for %s...", item_slug)
                plan_valid, plan_cost = _run_design_skill_validation(
                    skill_name="plan-validation.md",
                    input_artifacts={
                        "Design Document": design_doc_content,
                        "AC Register": requirements_content,
                    },
                    output_artifact=plan_content,
                    slug=item_slug,
                    step_number=6,
                    step_name="plan",
                )
                total_cost_usd += plan_cost
    elif design_doc_content:
        # Fallback: legacy design validation when no requirements available.
        logger.info("Running legacy design validation for %s...", item_slug)
        from langgraph_pipeline.pipeline.nodes.intake import _validate_design
        valid, reason, design_validation_cost = _validate_design(expected_design_doc_path, item_path)
        total_cost_usd += design_validation_cost
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
    # Copy plan and design to workspace if available
    ws_path = state.get("workspace_path")
    if ws_path:
        import shutil
        ws = Path(ws_path)
        try:
            if Path(expected_plan_path).exists():
                shutil.copy2(expected_plan_path, ws / "plan.yaml")
            if Path(expected_design_doc_path).exists():
                shutil.copy2(expected_design_doc_path, ws / "design.md")
        except OSError:
            pass  # Non-fatal

    prior_cost = float(state.get("session_cost_usd") or 0.0)
    return {
        "plan_path": expected_plan_path,
        "design_doc_path": expected_design_doc_path,
        "session_cost_usd": prior_cost + total_cost_usd,
    }
