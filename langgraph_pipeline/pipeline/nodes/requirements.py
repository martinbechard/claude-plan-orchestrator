# langgraph_pipeline/pipeline/nodes/requirements.py
# structure_requirements LangGraph node: transforms raw backlog input into structured,
# numbered requirements with an accept/reject validation loop.
# Design: docs/plans/2026-02-26-04-pipeline-graph-nodes-design.md

"""structure_requirements node for the pipeline StateGraph.

Sits between intake_analyze and create_plan. Reads the raw backlog item content,
calls Claude (Opus) to extract numbered requirements (P1, P2, ...) with type tags
and acceptance criteria, then validates nothing was lost using a Haiku reviewer
in an internal accept/reject loop (max 3 iterations).

Output: a structured requirements file at docs/plans/{date}-{slug}-requirements.md
containing the numbered requirements, a coverage matrix mapping raw input paragraphs
to requirement IDs, and a validation section showing the reviewer verdict.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

from langgraph_pipeline.pipeline.state import PipelineState
from langgraph_pipeline.shared.artifact_cache import is_artifact_fresh, record_artifact
from langgraph_pipeline.shared.claude_cli import call_claude
from langgraph_pipeline.shared.langsmith import add_trace_metadata
from langgraph_pipeline.shared.quota import detect_quota_exhaustion

# ─── Constants ────────────────────────────────────────────────────────────────

REQUIREMENTS_DIR = "docs/plans"
REQUIREMENTS_DATE_FORMAT = "%Y-%m-%d"

# Models: Opus for structuring (quality matters), Haiku for validation (fast check)
STRUCTURING_MODEL = "claude-opus-4-6"
REVIEWER_MODEL = "claude-haiku-4-5-20251001"


MAX_VALIDATION_ITERATIONS = 3

# ─── Prompt templates ─────────────────────────────────────────────────────────

STRUCTURING_PROMPT = (
    "You are a requirements analyst. Your job is to transform a raw backlog item "
    "into structured, numbered requirements. NOTHING from the raw input may be "
    "dropped or distorted.\n\n"
    "## Raw Input\n\n"
    "---\n{raw_content}\n---\n\n"
    "{clause_section}"
    "## Instructions\n\n"
    "Extract every requirement from the raw input using typed IDs:\n"
    "- **P<n>** (Problem): derived from C-PROB clauses -- something broken or wrong\n"
    "- **UC<n>** (Use Case): derived from C-GOAL clauses that describe a user workflow "
    "or interaction that should work (e.g., 'user should be able to X')\n"
    "- **FR<n>** (Feature Request): derived from C-GOAL clauses that request a new "
    "capability or system behavior (e.g., 'the system should backfill X')\n\n"
    "Decision rule: if the C-GOAL describes something a USER does, it is UC. "
    "If it describes something the SYSTEM does, it is FR.\n\n"
    "Each requirement gets:\n"
    "- An ID: P1, UC1, FR1, etc. (use the type that matches the source clauses)\n"
    "- A short title\n"
    "- A type tag: functional | UI | refactoring | performance | non-functional\n"
    "- A priority: high | medium | low\n"
    "- Source clauses: list of C<n> clause IDs from the Clause Register that this "
    "requirement addresses (e.g., Source clauses: [C1, C3])\n"
    "- A detailed description preserving all specifics from the raw input\n"
    "- Acceptance criteria as YES/NO questions (e.g., 'Does X work? YES = pass, NO = fail')\n\n"
    "IMPORTANT: C-PROB clauses MUST produce P<n> requirements. C-GOAL clauses MUST "
    "produce UC<n> or FR<n> requirements. A single item will typically have BOTH types.\n\n"
    "IMPORTANT: Every sentence and detail in the raw input MUST map to at least "
    "one requirement. Do not summarize or omit details.\n\n"
    "After listing requirements, include:\n"
    "1. A Coverage Matrix showing which raw input paragraphs map to which "
    "requirement IDs.\n"
    "2. A Clause Coverage Grid showing every C<n> and which requirement(s) it maps to. "
    "If a clause is not mapped, provide an explicit justification.\n\n"
    "## Output Format\n\n"
    "Respond with ONLY the structured requirements in this exact format:\n\n"
    "### P1: <title for a problem>\n"
    "Type: <type tag>\n"
    "Priority: <high|medium|low>\n"
    "Source clauses: [C1, C3]\n"
    "Description: <detailed description>\n"
    "Acceptance Criteria:\n"
    "- <question>? YES = pass, NO = fail\n\n"
    "### UC1: <title for a use case / user goal>\n"
    "Type: <type tag>\n"
    "Priority: <high|medium|low>\n"
    "Source clauses: [C4, C9]\n"
    "Description: <detailed description>\n"
    "Acceptance Criteria:\n"
    "- <question>? YES = pass, NO = fail\n\n"
    "### FR1: <title for a feature request>\n"
    "...\n\n"
    "## Coverage Matrix\n"
    "| Raw Input Section | Requirement(s) |\n"
    "|---|---|\n"
    "| <quote or description of raw input section> | P1, P3 |\n"
    "...\n\n"
    "## Clause Coverage Grid\n"
    "| Clause | Type | Mapped To | Status |\n"
    "|---|---|---|---|\n"
    "| C1 [PROB] | PROB | P1 | Mapped |\n"
    "| C4 [GOAL] | GOAL | UC1 | Mapped |\n"
    "| C9 [GOAL] | GOAL | FR1 | Mapped |\n"
    "| C5 [CTX] | CTX | -- | Unmapped: context only |\n"
    "...\n"
)

CLAUSE_SECTION_TEMPLATE = (
    "## Clause Register\n\n"
    "The following clauses were extracted from the raw input. Each requirement "
    "MUST reference its source clause IDs.\n\n"
    "---\n{clause_content}\n---\n\n"
)

AC_GENERATION_PROMPT = (
    "You are a requirements analyst. Generate acceptance criteria from the "
    "structured requirements and clause register below.\n\n"
    "## Clause Register\n\n"
    "---\n{clause_content}\n---\n\n"
    "## Structured Requirements\n\n"
    "---\n{requirements_content}\n---\n\n"
    "## Instructions\n\n"
    "Generate numbered acceptance criteria (AC1, AC2, ...). Each AC must:\n"
    "- Be a YES/NO verifiable question\n"
    "- Declare its origin:\n"
    "  - Explicit: C-AC clause text preserved verbatim\n"
    "  - Derived from C-PROB: inverted ('X is broken' -> 'Is X working?')\n"
    "  - Derived from C-GOAL: made testable ('user should X' -> 'Can user X?')\n"
    "- Declare which requirement (P<n>, UC<n>, or FR<n>) it belongs to\n"
    "- List source clauses [C<n>]\n\n"
    "Rules:\n"
    "- Every C-AC clause must appear verbatim as an AC\n"
    "- Every C-PROB clause must have at least one derived AC\n"
    "- Every C-GOAL clause must have at least one derived AC\n"
    "- Every requirement (P<n>, UC<n>, FR<n>) must have at least one AC\n"
    "- C-FACT and C-CTX clauses without ACs need explicit justification\n\n"
    "## Output Format\n\n"
    "## Acceptance Criteria\n\n"
    "AC1: <question>? YES = pass, NO = fail\n"
    "  Origin: <Explicit from C3 | Derived from C1 [PROB] (inverse) | Derived from C4 [GOAL] (operationalized)>\n"
    "  Belongs to: P1\n"
    "  Source clauses: [C1, C2]\n\n"
    "AC2: <question>? YES = pass, NO = fail\n"
    "  Origin: Derived from C4 [GOAL] (operationalized)\n"
    "  Belongs to: UC1\n"
    "  Source clauses: [C4]\n\n"
    "AC3: ...\n\n"
    "## Requirement -> AC Coverage\n"
    "| Requirement | ACs | Count |\n"
    "|---|---|---|\n"
    "| P1 | AC1 | 1 |\n"
    "| UC1 | AC2 | 1 |\n"
    "| FR1 | AC3 | 1 |\n\n"
    "## Clause -> AC Coverage\n"
    "| Clause | Type | AC | How |\n"
    "|---|---|---|---|\n"
    "| C1 | PROB | AC1 | Inverse |\n"
    "| C4 | GOAL | AC2 | Made testable |\n"
    "| C5 | CTX | -- | Context, not testable |\n"
)

STRUCTURING_RETRY_PROMPT = (
    "You are a requirements analyst. Your previous attempt to structure requirements "
    "was REJECTED by the reviewer because information was lost.\n\n"
    "## Raw Input\n\n"
    "---\n{raw_content}\n---\n\n"
    "## Your Previous Output\n\n"
    "---\n{previous_output}\n---\n\n"
    "## Reviewer Rejection\n\n"
    "{rejection_feedback}\n\n"
    "## Instructions\n\n"
    "Fix the structured requirements to address the reviewer's feedback. "
    "Make sure EVERY detail from the raw input is captured. "
    "Use the same output format as before (P<n>, UC<n>, FR<n> with Coverage Matrix "
    "and Clause Coverage Grid). Remember: C-PROB clauses produce P<n>, "
    "C-GOAL clauses produce UC<n> or FR<n>.\n"
)

REVIEWER_PROMPT = (
    "You are a requirements reviewer. Compare the structured requirements against "
    "the raw input and determine if anything was lost or distorted.\n\n"
    "## Raw Input\n\n"
    "---\n{raw_content}\n---\n\n"
    "## Structured Requirements\n\n"
    "---\n{structured_output}\n---\n\n"
    "## Instructions\n\n"
    "Check carefully:\n"
    "1. Is every piece of information from the raw input captured in at least one "
    "requirement?\n"
    "2. Are the acceptance criteria specific and verifiable (YES/NO questions)?\n"
    "3. Is anything distorted or reinterpreted incorrectly?\n"
    "4. Are requirement types correct? Problems (broken things) should be P<n>, "
    "user workflows should be UC<n>, new system capabilities should be FR<n>. "
    "If C-GOAL clauses are mapped only to P<n> requirements, that is WRONG.\n\n"
    "If everything is captured accurately, respond with exactly: ACCEPT\n\n"
    "If anything is missing or distorted, respond with:\n"
    "REJECT\n"
    "Then list each missing or distorted item on its own line, starting with '- '.\n"
)

# ─── Helpers ──────────────────────────────────────────────────────────────────


def _read_file_content(path: str) -> str:
    """Read file content. Returns empty string on error."""
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return ""


def _save_subprocess_output(slug: str, phase: str, stdout: str, stderr: str, exit_code: int) -> None:
    """Save subprocess stdout/stderr to the per-item output directory."""
    try:
        from langgraph_pipeline.shared.paths import WORKER_OUTPUT_DIR
        output_dir = WORKER_OUTPUT_DIR / slug
        output_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d-%H%M%S")
        log_path = output_dir / f"{phase}-{ts}.log"
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(f"=== {phase} for {slug} ===\n")
            f.write(f"Exit code: {exit_code}\n\n")
            f.write("=== STDOUT ===\n")
            f.write(stdout or "")
            f.write("\n=== STDERR ===\n")
            f.write(stderr or "")
    except Exception:
        pass  # Non-fatal


def _call_llm(prompt: str, model: str,
              slug: str = "", phase: str = "requirements") -> tuple[str, float, str]:
    """Call Claude via shared call_claude. Returns (text, cost, failure_reason).

    failure_reason is empty on success. On failure, text is empty and
    failure_reason contains a description of what went wrong.
    """
    result = call_claude(prompt, model=model)
    if slug and result.raw_stdout:
        _save_subprocess_output(slug, phase, result.raw_stdout,
                                result.failure_reason or "", 0 if not result.failure_reason else 1)
    if result.failure_reason:
        return "", 0.0, result.failure_reason
    return result.text, result.total_cost_usd, ""


def _build_requirements_doc(
    item_name: str, item_path: str, structured_output: str,
    iterations: int, reviewer_notes: str,
) -> str:
    """Build the structured requirements markdown document."""
    timestamp = datetime.now(tz=timezone.utc).isoformat()
    return (
        f"# Structured Requirements: {item_name}\n\n"
        f"Source: {item_path}\n"
        f"Generated: {timestamp}\n\n"
        f"## Requirements\n\n"
        f"{structured_output}\n\n"
        f"## Validation\n\n"
        f"Status: ACCEPTED\n"
        f"Iterations: {iterations}\n"
        f"Reviewer notes: {reviewer_notes}\n"
    )


def _run_skill_validation(
    skill_name: str,
    input_artifacts: dict[str, str],
    output_artifact: str,
    slug: str,
    step_number: int,
    step_name: str,
) -> tuple[bool, float]:
    """Run skill-based cross-reference validation and save the report.

    Returns (valid, cost). Non-blocking: logs warnings on failure but does not
    prevent the pipeline from proceeding.
    """
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
    output, cost, failure_reason = _call_llm(
        prompt, model=REVIEWER_MODEL,
        slug=slug, phase=f"validation-step-{step_number}",
    )
    if failure_reason:
        logger.warning("Step %d validation failed for %s: %s", step_number, slug, failure_reason)
        return False, cost

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


def structure_requirements(state: PipelineState) -> dict:
    """LangGraph node: transform raw backlog item into structured requirements.

    Short-circuits when requirements_path or plan_path is already set
    (in-progress resumption from a prior pipeline run).

    Process:
    1. Read raw backlog item content
    2. Call Opus to extract numbered requirements (P1, P2, ...)
    3. Internal validation loop (max 3 iterations):
       - Call Haiku reviewer to check nothing was lost
       - If REJECT: re-prompt Opus with rejection feedback
       - If ACCEPT: proceed
    4. Save structured requirements to docs/plans/{date}-{slug}-requirements.md
    5. Return {"requirements_path": path}
    """
    item_path: str = state.get("item_path", "")
    item_slug: str = state.get("item_slug", "")
    item_name: str = state.get("item_name", item_slug)
    requirements_path: Optional[str] = state.get("requirements_path")
    plan_path: Optional[str] = state.get("plan_path")

    # Short-circuit: requirements or plan already exist (resumption).
    if requirements_path and Path(requirements_path).exists():
        return {}
    if plan_path:
        return {}

    workspace_path: Optional[str] = state.get("workspace_path")
    clause_register_path: Optional[str] = state.get("clause_register_path")
    five_whys_path: Optional[str] = state.get("five_whys_path")

    # Freshness check: skip if workspace/requirements.md is up-to-date relative to inputs.
    if workspace_path and clause_register_path and five_whys_path:
        if is_artifact_fresh(workspace_path, "requirements.md", [clause_register_path, five_whys_path]):
            existing_reqs = sorted(Path(REQUIREMENTS_DIR).glob(f"*-{item_slug}-requirements.md"))
            if existing_reqs:
                logger.info("Requirements fresh for %s — skipping step", item_slug)
                return {"requirements_path": str(existing_reqs[-1])}

    raw_content = _read_file_content(item_path)
    if not raw_content:
        logger.warning("Cannot read item file at %s — skipping requirements structuring", item_path)
        return {}

    # Load clause register if available for traceability.
    clause_content = ""
    if clause_register_path:
        clause_content = _read_file_content(clause_register_path)
    clause_section = CLAUSE_SECTION_TEMPLATE.format(clause_content=clause_content) if clause_content else ""

    total_cost_usd: float = 0.0
    structured_output = ""
    reviewer_notes = ""
    iterations = 0

    # Step 1: Initial structuring call (Opus)
    logger.info("Structuring requirements for %s...", item_slug)
    prompt = STRUCTURING_PROMPT.format(raw_content=raw_content, clause_section=clause_section)
    text, cost, failure_reason = _call_llm(
        prompt, model=STRUCTURING_MODEL,
        slug=item_slug, phase="requirements-structure",
    )
    total_cost_usd += cost

    if failure_reason:
        logger.warning("Requirements structuring failed for %s: %s", item_slug, failure_reason)
        if detect_quota_exhaustion(failure_reason):
            return {"quota_exhausted": True}
        return {}

    structured_output = text
    iterations = 1

    # Step 2: Validation loop (Haiku reviewer, max iterations)
    for iteration in range(MAX_VALIDATION_ITERATIONS):
        logger.info("Requirements review iteration %d/%d for %s",
                     iteration + 1, MAX_VALIDATION_ITERATIONS, item_slug)

        review_prompt = REVIEWER_PROMPT.format(
            raw_content=raw_content,
            structured_output=structured_output,
        )
        review_text, review_cost, review_failure = _call_llm(
            review_prompt, model=REVIEWER_MODEL,
            slug=item_slug, phase=f"requirements-review-{iteration + 1}",
        )
        total_cost_usd += review_cost

        if review_failure:
            logger.warning("Requirements review failed for %s: %s", item_slug, review_failure)
            if detect_quota_exhaustion(review_failure):
                return {"quota_exhausted": True}
            # Reviewer failure is non-fatal — accept current output
            reviewer_notes = f"Reviewer unavailable (iteration {iteration + 1}): {review_failure}"
            break

        review_verdict = review_text.strip()
        if review_verdict.upper().startswith("ACCEPT"):
            logger.info("Requirements ACCEPTED for %s after %d iteration(s)", item_slug, iteration + 1)
            reviewer_notes = review_verdict
            break

        # REJECT — extract feedback and retry
        rejection_feedback = review_verdict
        logger.info("Requirements REJECTED for %s (iteration %d): %s",
                     item_slug, iteration + 1, rejection_feedback[:200])

        # Don't retry on last iteration
        if iteration == MAX_VALIDATION_ITERATIONS - 1:
            logger.warning("Max validation iterations reached for %s — accepting current output", item_slug)
            reviewer_notes = f"Max iterations reached. Last rejection: {rejection_feedback[:500]}"
            break

        # Retry with rejection feedback
        retry_prompt = STRUCTURING_RETRY_PROMPT.format(
            raw_content=raw_content,
            previous_output=structured_output,
            rejection_feedback=rejection_feedback,
        )
        retry_text, retry_cost, retry_failure = _call_llm(
            retry_prompt, model=STRUCTURING_MODEL,
            slug=item_slug, phase=f"requirements-retry-{iteration + 1}",
        )
        total_cost_usd += retry_cost
        iterations += 1

        if retry_failure:
            logger.warning("Requirements retry failed for %s: %s", item_slug, retry_failure)
            if detect_quota_exhaustion(retry_failure):
                return {"quota_exhausted": True}
            reviewer_notes = f"Retry failed (iteration {iteration + 1}): {retry_failure}"
            break

        structured_output = retry_text

    # Step 3: Save requirements document
    date_str = datetime.now().strftime(REQUIREMENTS_DATE_FORMAT)
    requirements_file = f"{REQUIREMENTS_DIR}/{date_str}-{item_slug}-requirements.md"
    requirements_doc = _build_requirements_doc(
        item_name=item_name,
        item_path=item_path,
        structured_output=structured_output,
        iterations=iterations,
        reviewer_notes=reviewer_notes,
    )

    try:
        req_path = Path(requirements_file)
        req_path.parent.mkdir(parents=True, exist_ok=True)
        req_path.write_text(requirements_doc, encoding="utf-8")
        logger.info("Structured requirements saved to %s", requirements_file)
    except OSError as exc:
        logger.warning("Failed to write requirements file %s: %s", requirements_file, exc)
        return {}

    # Also write to workspace if available
    if workspace_path:
        try:
            ws_req = Path(workspace_path) / "requirements.md"
            ws_req.write_text(requirements_doc, encoding="utf-8")
        except OSError:
            pass  # Non-fatal

    # Step 3b: Skill-based validation of requirements structuring (Step 3).
    if clause_content:
        _run_skill_validation(
            skill_name="requirements-structuring-validation.md",
            input_artifacts={"Clause Register": clause_content},
            output_artifact=structured_output,
            slug=item_slug,
            step_number=3,
            step_name="requirements-structuring",
        )

    # Step 4: Generate AC Register from clause register + structured requirements.
    ac_section = ""
    if clause_content:
        logger.info("Generating AC Register for %s...", item_slug)
        ac_prompt = AC_GENERATION_PROMPT.format(
            clause_content=clause_content,
            requirements_content=structured_output,
        )
        ac_text, ac_cost, ac_failure = _call_llm(
            ac_prompt, model=STRUCTURING_MODEL,
            slug=item_slug, phase="requirements-ac-generation",
        )
        total_cost_usd += ac_cost

        if ac_failure:
            logger.warning("AC generation failed for %s: %s", item_slug, ac_failure)
        else:
            ac_section = ac_text

            # Append AC Register to requirements file.
            try:
                with open(requirements_file, "a", encoding="utf-8") as f:
                    f.write(f"\n\n{ac_section}\n")
                logger.info("AC Register appended to %s", requirements_file)
                # Update workspace copy.
                if workspace_path:
                    try:
                        ws_req = Path(workspace_path) / "requirements.md"
                        with open(ws_req, "a", encoding="utf-8") as f:
                            f.write(f"\n\n{ac_section}\n")
                    except OSError:
                        pass
            except OSError as exc:
                logger.warning("Failed to append AC Register: %s", exc)

            # Skill-based validation of AC generation (Step 4).
            _run_skill_validation(
                skill_name="ac-generation-validation.md",
                input_artifacts={
                    "Clause Register": clause_content,
                    "Structured Requirements": structured_output,
                },
                output_artifact=ac_section,
                slug=item_slug,
                step_number=4,
                step_name="ac-generation",
            )

    # Record input hashes so future restarts can detect staleness.
    if workspace_path and clause_register_path and five_whys_path:
        try:
            record_artifact(workspace_path, "requirements.md", [clause_register_path, five_whys_path])
        except Exception:
            pass  # Non-fatal

    add_trace_metadata({
        "node_name": "structure_requirements",
        "graph_level": "pipeline",
        "item_slug": item_slug,
        "total_cost_usd": total_cost_usd,
        "validation_iterations": iterations,
    })

    prior_cost = float(state.get("session_cost_usd") or 0.0)
    return {
        "requirements_path": requirements_file,
        "session_cost_usd": prior_cost + total_cost_usd,
    }
