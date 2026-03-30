# langgraph_pipeline/pipeline/nodes/intake.py
# intake_analyze LangGraph node: pre-planning analysis, throttle, and quality gates.
# Design: docs/plans/2026-02-26-04-pipeline-graph-nodes-design.md

"""intake_analyze node for the pipeline StateGraph.

Analyzes each backlog item before plan creation:
  - Defects:   spawn Claude to verify symptoms are still reproducible.
  - Analyses:  spawn Claude to run a 5-Whys root-cause classification.
  - Features:  pass through (no pre-analysis needed).

Safety gates (non-blocking for existing backlog items):
  - Disk-persisted throttle: prevents runaway creation of new items.
  - Clarity gate: warns when item description falls below the threshold.
  - RAG deduplication: logs warnings when semantically similar items exist.

The throttle file lives on disk (tmp/plans/.backlog-creation-throttle.json)
so it survives LangGraph checkpoint restarts and process crashes.
"""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

from langgraph_pipeline.pipeline.state import PipelineState
from langgraph_pipeline.shared.claude_cli import call_claude
from langgraph_pipeline.shared.langsmith import add_trace_metadata
from langgraph_pipeline.shared.quota import detect_quota_exhaustion
from langgraph_pipeline.shared.shutdown import get_shutdown_event

# ─── Constants ────────────────────────────────────────────────────────────────

THROTTLE_FILE_PATH = "tmp/plans/.backlog-creation-throttle.json"
THROTTLE_WINDOW_SECONDS = 3600  # 1-hour rolling window

# Maximum new items to create per type per hour.
MAX_INTAKES_PER_HOUR: dict[str, int] = {
    "defect": 50,
    "feature": 50,
    "analysis": 50,
}

# Seconds between re-checks when the throttle wait loop is active.
THROTTLE_WAIT_INTERVAL_SECONDS = 60

# Reject requests below this clarity level (1–5 scale).
INTAKE_CLARITY_THRESHOLD = 3

# Timeout for Claude subprocess calls during intake analysis.
INTAKE_MODEL = "claude-haiku-4-5-20251001"  # Haiku sufficient for classification tasks

# Similarity threshold for RAG deduplication (0.0 – 1.0).
RAG_SIMILARITY_THRESHOLD = 0.75

# Maximum retries for clause extraction / 5 Whys validation failures.
MAX_ANALYTICAL_VALIDATION_RETRIES = 2

# Regex patterns for parsing Claude output fields.
_CLARITY_PATTERN = re.compile(r"Clarity:\s*([1-5])", re.IGNORECASE)
_REPRODUCIBLE_PATTERN = re.compile(r"Reproducible:\s*(yes|no|unclear)", re.IGNORECASE)

# ─── Prompt templates ─────────────────────────────────────────────────────────

CLAUSE_EXTRACTION_PROMPT = (
    "You are a requirements analyst. Parse the following backlog item into "
    "individually meaningful clauses. Each clause is a single statement from "
    "the original text.\n\n"
    "## Raw Input\n\n"
    "---\n{item_content}\n---\n\n"
    "## Instructions\n\n"
    "For each independently meaningful statement in the raw input:\n"
    "1. Assign a sequential ID: C1, C2, C3, ...\n"
    "2. Assign exactly one type code:\n"
    "   - C-PROB: Something broken or wrong\n"
    "   - C-FACT: Verifiable current state / observation\n"
    "   - C-GOAL: Desired outcome / what the user wants\n"
    "   - C-CONS: Constraint or limitation on the solution\n"
    "   - C-CTX: Context or background information\n"
    "   - C-AC: Explicit pass/fail acceptance criterion from the user\n"
    "3. Preserve the exact wording -- do NOT paraphrase or interpret\n"
    "4. If a statement is ambiguous, flag it: [AMBIGUOUS]\n\n"
    "IMPORTANT: Respond with ONLY the clause register below. No preamble, "
    "no commentary, no explanation. Start directly with ## Clause Register.\n\n"
    "## Output Format\n\n"
    "## Clause Register\n\n"
    "C1 [TYPE]: exact text from input\n"
    "C2 [TYPE]: exact text from input\n"
    "...\n\n"
    "## Summary\n"
    "Total clauses: N\n"
    "By type: N PROB, N FACT, N GOAL, N CONS, N CTX, N AC\n"
)

FIVE_WHYS_WITH_CLAUSES_PROMPT = (
    "Analyze this {item_type} backlog item using the 5 Whys method.\n\n"
    "## Clause Register\n\n"
    "---\n{clause_register}\n---\n\n"
    "## Raw Backlog Item\n\n"
    "---\n{item_content}\n---\n\n"
    "Perform a 5 Whys analysis to uncover the root need behind this request.\n"
    "IMPORTANT: Each Why MUST reference specific clause IDs (C1, C2, ...) as evidence.\n"
    "If a Why introduces information not in any clause, mark it: [ASSUMPTION]\n\n"
    "Respond in this exact format:\n\n"
    "Title: <one-line title>\n"
    "Clarity: <1-5 integer rating of the original request clarity>\n"
    "5 Whys:\n"
    "W1: <why question>\n"
    "    Because: <answer> [C1, C3]\n"
    "W2: <why question>\n"
    "    Because: <answer> [C5]\n"
    "W3: <why question>\n"
    "    Because: <answer> [C2, C4]\n"
    "W4: <why question>\n"
    "    Because: <answer> [C6]\n"
    "W5: <why question>\n"
    "    Because: <answer> [C7] [ASSUMPTION]\n\n"
    "Root Need: <root need referencing C-PROB and C-GOAL clauses> [C1, C4]\n"
    "Summary: <one-sentence summary>"
)

DEFECT_SYMPTOM_PROMPT = (
    "You are analyzing a defect backlog item to verify symptoms are still present.\n\n"
    "Here is the defect backlog item:\n\n---\n{item_content}\n---\n\n"
    "Your task:\n"
    "1. Read and understand the reported symptoms.\n"
    "2. Determine whether the symptoms are clearly described and actionable.\n"
    "3. Note whether any related code or tests provide evidence the issue is still current.\n\n"
    "Respond in this exact format:\n\n"
    "Reproducible: <yes|no|unclear>\n"
    "Clarity: <1-5 integer>\n"
    "Summary: <one sentence describing the defect and its apparent status>"
)

CHECK_HAS_FIVE_WHYS_PROMPT = (
    "Here is a backlog item:\n\n---\n{item_content}\n---\n\n"
    "Does this item already contain a 5 Whys analysis (5 numbered Why "
    "questions with answers and a Root Need)?\n\n"
    "Respond with ONLY one word: YES or NO"
)

CHECK_HAS_ACCEPTANCE_CHECKLIST_PROMPT = (
    "Here is a design document:\n\n---\n{design_content}\n---\n\n"
    "Does this design document contain acceptance criteria written as a "
    "checklist of specific YES/NO questions (e.g. 'Does X work? YES = pass, "
    "NO = fail')?\n\n"
    "Respond with ONLY one word: YES or NO"
)

DESIGN_VALIDATOR_MODEL = "claude-opus-4-6"

VALIDATE_FIVE_WHYS_PROMPT = (
    "Here is a backlog item:\n\n---\n{item_content}\n---\n\n"
    "This item contains a 5 Whys analysis. Validate its quality:\n\n"
    "1. Does each Why logically follow from the previous answer, with no "
    "unjustified assumptions or leaps in reasoning?\n"
    "2. Does the Root Need / final conclusion actually match and address "
    "the original user request at the top of the item?\n"
    "3. Are there any non-sequiturs where a Why introduces a new topic "
    "not supported by the previous answer?\n\n"
    "If the 5 Whys are valid, respond: VALID\n"
    "If there are problems, respond: INVALID\n"
    "Then on the next line explain what is wrong in one sentence."
)

VALIDATE_DESIGN_PROMPT = (
    "Here is a design document:\n\n---\n{design_content}\n---\n\n"
    "Here is the original backlog item:\n\n---\n{item_content}\n---\n\n"
    "Validate the design:\n\n"
    "1. Does the design contain acceptance criteria as a checklist of "
    "specific YES/NO questions?\n"
    "2. Does the design actually address the original user request in the "
    "backlog item, or does it solve a different problem?\n"
    "3. Are there any unjustified assumptions or solutions that the user "
    "did not ask for?\n\n"
    "If the design is valid, respond: VALID\n"
    "If there are problems, respond: INVALID\n"
    "Then on the next line explain what is wrong in one sentence."
)

FIVE_WHYS_PROMPT = (
    "Analyze this {item_type} backlog item using the 5 Whys method.\n\n"
    "Here is the backlog item:\n\n---\n{item_content}\n---\n\n"
    "Perform a 5 Whys analysis to uncover the root need behind this request.\n"
    "IMPORTANT: Provide exactly 5 numbered Why questions and answers. Each Why\n"
    "should dig deeper into the root cause of the previous answer.\n\n"
    "Respond in this exact format:\n\n"
    "Title: <one-line title>\n"
    "Clarity: <1-5 integer rating of the original request clarity>\n"
    "5 Whys:\n"
    "1. <why>\n"
    "2. <why>\n"
    "3. <why>\n"
    "4. <why>\n"
    "5. <why>\n\n"
    "Root Need: <root need uncovered by the analysis>\n"
    "Summary: <one-sentence summary>"
)

# ─── Throttle helpers ─────────────────────────────────────────────────────────


def _read_throttle() -> dict[str, list[str]]:
    """Read the disk-persisted backlog creation throttle file.

    Returns a dict mapping item_type to a list of ISO-8601 timestamp strings.
    Returns an empty dict if the file does not exist or cannot be parsed.
    """
    try:
        with open(THROTTLE_FILE_PATH, "r") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (IOError, json.JSONDecodeError):
        return {}


def _write_throttle(data: dict[str, list[str]]) -> None:
    """Write the throttle dict to disk, creating parent directories as needed."""
    try:
        Path(THROTTLE_FILE_PATH).parent.mkdir(parents=True, exist_ok=True)
        with open(THROTTLE_FILE_PATH, "w") as f:
            json.dump(data, f)
    except IOError:
        pass  # Throttle write failures are non-fatal.


def _check_throttle(item_type: str) -> bool:
    """Return True if creating a new item of item_type is currently throttled.

    Prunes timestamps outside the rolling window before checking the count.
    """
    max_count = MAX_INTAKES_PER_HOUR.get(item_type, 10)
    throttle = _read_throttle()
    entries: list[str] = throttle.get(item_type, [])

    now_ts = datetime.now(tz=timezone.utc).timestamp()
    cutoff = now_ts - THROTTLE_WINDOW_SECONDS

    recent = [ts for ts in entries if _parse_timestamp(ts) >= cutoff]
    return len(recent) >= max_count


def _record_intake(item_type: str) -> None:
    """Record an intake event for item_type in the disk-persisted throttle."""
    throttle = _read_throttle()
    entries: list[str] = throttle.get(item_type, [])

    now_ts = datetime.now(tz=timezone.utc).timestamp()
    cutoff = now_ts - THROTTLE_WINDOW_SECONDS

    # Prune old entries before appending.
    pruned = [ts for ts in entries if _parse_timestamp(ts) >= cutoff]
    pruned.append(datetime.now(tz=timezone.utc).isoformat())

    throttle[item_type] = pruned
    _write_throttle(throttle)


def _parse_timestamp(ts: str) -> float:
    """Parse an ISO-8601 timestamp string to a POSIX float. Returns 0.0 on failure."""
    try:
        return datetime.fromisoformat(ts).timestamp()
    except (ValueError, TypeError):
        return 0.0


# ─── Claude invocation ────────────────────────────────────────────────────────


def _call_llm(prompt: str, model: str = INTAKE_MODEL,
              slug: str = "", phase: str = "intake") -> tuple[str, float, str]:
    """Call Claude via shared call_claude. Returns (text, cost, failure_reason).

    failure_reason is an empty string on success. On failure, text is empty
    and failure_reason contains a description of what went wrong. Callers must
    check failure_reason before treating text as valid analysis output.
    """
    result = call_claude(prompt, model=model)
    if slug and result.raw_stdout:
        _save_subprocess_output(slug, phase, result.raw_stdout,
                                result.failure_reason or "", 0 if not result.failure_reason else 1)
    # Token/cost reporting is handled by call_claude via POST /api/worker-stats
    if result.failure_reason:
        return "", 0.0, result.failure_reason
    return result.text, result.total_cost_usd, ""


# ─── Analysis helpers ─────────────────────────────────────────────────────────


def _parse_clarity_score(output: str) -> int:
    """Extract the Clarity score (1–5) from Claude analysis output.

    Returns INTAKE_CLARITY_THRESHOLD if the score cannot be parsed,
    which keeps borderline items from being incorrectly blocked.
    """
    match = _CLARITY_PATTERN.search(output)
    if match:
        return int(match.group(1))
    return INTAKE_CLARITY_THRESHOLD


def _check_rag_dedup(slug: str) -> bool:
    """Return True if a semantically similar item already exists in ChromaDB.

    Requires the optional 'chromadb' package. Returns False (no duplicate) when
    ChromaDB is unavailable, so the pipeline proceeds without dedup.
    """
    try:
        import chromadb  # type: ignore[import-not-found]
    except ImportError:
        return False

    try:
        client = chromadb.PersistentClient(path=".chroma")
        collection = client.get_collection("backlog")
        results = collection.query(query_texts=[slug], n_results=1)
        distances: list[list[float]] = results.get("distances") or [[]]
        if distances and distances[0]:
            similarity = 1.0 - distances[0][0]
            return similarity >= RAG_SIMILARITY_THRESHOLD
    except Exception:  # noqa: BLE001 — ChromaDB errors should not block the pipeline.
        pass

    return False


def _verify_defect_symptoms(item_path: str) -> dict[str, str | int | float | bool]:
    """Spawn Claude to verify defect symptoms and return parsed result fields.

    Returns a dict with a "failed" key (bool). When failed=True, raw_output is
    empty and failure_reason contains the error description. Callers must check
    "failed" before treating raw_output as valid analysis.
    """
    content = _read_file_content(item_path)
    prompt = DEFECT_SYMPTOM_PROMPT.format(item_content=content)
    output, cost, failure_reason = _call_llm(prompt)
    if failure_reason:
        return {
            "failed": True,
            "failure_reason": failure_reason,
            "reproducible": "unclear",
            "clarity": INTAKE_CLARITY_THRESHOLD,
            "raw_output": "",
            "total_cost_usd": 0.0,
        }
    clarity = _parse_clarity_score(output)
    reproducible_match = _REPRODUCIBLE_PATTERN.search(output)
    reproducible = reproducible_match.group(1).lower() if reproducible_match else "unclear"
    return {"failed": False, "reproducible": reproducible, "clarity": clarity, "raw_output": output, "total_cost_usd": cost}




def _has_five_whys(item_path: str) -> bool:
    """Use Haiku to check if the backlog item already contains a 5 Whys analysis.

    Returns False on LLM failure (safe default: assume 5 Whys not yet present).
    """
    content = _read_file_content(item_path)
    if not content:
        return False
    prompt = CHECK_HAS_FIVE_WHYS_PROMPT.format(item_content=content)
    output, _cost, failure_reason = _call_llm(prompt)
    if failure_reason:
        return False
    return output.strip().upper().startswith("YES")


def _validate_five_whys(item_path: str) -> tuple[bool, str, float]:
    """Use Opus to validate 5 Whys quality — no unjustified assumptions, conclusion matches request."""
    content = _read_file_content(item_path)
    if not content:
        return False, "Could not read item file", 0.0
    prompt = VALIDATE_FIVE_WHYS_PROMPT.format(item_content=content)
    output, cost, failure_reason = _call_llm(prompt, model=DESIGN_VALIDATOR_MODEL)
    if failure_reason:
        return False, failure_reason, cost
    valid = output.strip().upper().startswith("VALID")
    reason = output.strip().split("\n", 1)[1].strip() if "\n" in output.strip() else ""
    return valid, reason, cost


def _validate_design(design_doc_path: str, item_path: str) -> tuple[bool, str, float]:
    """Use Opus to validate design — has checklist, matches request, no unjustified assumptions."""
    design_content = _read_file_content(design_doc_path)
    item_content = _read_file_content(item_path)
    if not design_content:
        return False, "Could not read design doc", 0.0
    if not item_content:
        return False, "Could not read item file", 0.0
    prompt = VALIDATE_DESIGN_PROMPT.format(design_content=design_content, item_content=item_content)
    output, cost, failure_reason = _call_llm(prompt, model=DESIGN_VALIDATOR_MODEL)
    if failure_reason:
        return False, failure_reason, cost
    valid = output.strip().upper().startswith("VALID")
    reason = output.strip().split("\n", 1)[1].strip() if "\n" in output.strip() else ""
    return valid, reason, cost


def _has_acceptance_checklist(design_doc_path: str) -> bool:
    """Use Haiku to check if the design doc contains YES/NO acceptance criteria."""
    content = _read_file_content(design_doc_path)
    if not content:
        return False
    prompt = CHECK_HAS_ACCEPTANCE_CHECKLIST_PROMPT.format(design_content=content)
    output, _cost, failure_reason = _call_llm(prompt)
    if failure_reason:
        return False  # Safe default: assume checklist not present
    return output.strip().upper().startswith("YES")


def _report_intake_error(msg: str) -> None:
    """Report an intake error to the dashboard notification stream if available."""
    try:
        from langgraph_pipeline.web.dashboard_state import get_dashboard_state
        get_dashboard_state().add_notification(msg)
    except Exception:
        pass


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


def _read_file_content(path: str) -> str:
    """Read file content. Returns empty string on error."""
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return ""


def _append_analysis_to_item(item_path: str, analysis_text: str) -> None:
    """Append the 5 Whys analysis text to the end of the backlog item file."""
    if not analysis_text or not analysis_text.strip():
        return
    try:
        with open(item_path, "a", encoding="utf-8") as f:
            f.write("\n\n## 5 Whys Analysis\n\n")
            f.write(analysis_text.strip())
            f.write("\n")
        logger.info("Appended 5 Whys analysis to %s", item_path)
    except OSError as exc:
        logger.warning("Failed to append analysis to %s: %s", item_path, exc)


def _run_clause_extraction(item_path: str, slug: str = "") -> dict[str, str | float | bool]:
    """Spawn Claude to extract clauses from the raw backlog item.

    Returns a dict with 'failed', 'raw_output', 'total_cost_usd', and 'failure_reason'.
    """
    content = _read_file_content(item_path)
    if not content:
        return {"failed": True, "failure_reason": "Empty item file", "raw_output": "", "total_cost_usd": 0.0}
    prompt = CLAUSE_EXTRACTION_PROMPT.format(item_content=content)
    output, cost, failure_reason = _call_llm(prompt, slug=slug, phase="intake-clause-extraction")
    if failure_reason:
        return {"failed": True, "failure_reason": failure_reason, "raw_output": "", "total_cost_usd": 0.0}
    return {"failed": False, "failure_reason": "", "raw_output": output, "total_cost_usd": cost}


def _save_clause_register(slug: str, clause_content: str) -> str:
    """Save clause register to workspace and return the file path.

    Strips any LLM preamble before the ## Clause Register header.
    """
    from langgraph_pipeline.shared.paths import ensure_workspace
    # Strip preamble — the register should start at ## Clause Register
    marker = "## Clause Register"
    idx = clause_content.find(marker)
    if idx > 0:
        clause_content = clause_content[idx:]
    ws = ensure_workspace(slug)
    clause_path = ws / "clauses.md"
    clause_path.write_text(clause_content, encoding="utf-8")
    logger.info("Saved clause register to %s", clause_path)
    return str(clause_path)


def _save_five_whys(slug: str, whys_content: str) -> str:
    """Save 5 Whys analysis to workspace and return the file path."""
    from langgraph_pipeline.shared.paths import ensure_workspace
    ws = ensure_workspace(slug)
    whys_path = ws / "five-whys.md"
    whys_path.write_text(whys_content, encoding="utf-8")
    logger.info("Saved 5 Whys analysis to %s", whys_path)
    return str(whys_path)


def _validate_with_skill(
    skill_name: str,
    input_artifacts: dict[str, str],
    output_artifact: str,
    slug: str,
    step_number: int,
    step_name: str,
) -> tuple[bool, str, float]:
    """Run skill-based validation by loading a skill file and prompting the LLM.

    Args:
        skill_name: Filename of the validation skill (e.g. 'clause-extraction-validation.md').
        input_artifacts: Dict mapping artifact names to their content.
        output_artifact: The content of the artifact being validated.
        slug: Item slug for saving the cross-reference report.
        step_number: Pipeline step number (1-8).
        step_name: Short kebab-case name for the step.

    Returns:
        Tuple of (valid, reason, cost). valid is True if the skill validation passed.
    """
    from langgraph_pipeline.shared.traceability import load_validation_skill, save_cross_reference_report

    try:
        skill_content = load_validation_skill(skill_name)
    except FileNotFoundError:
        logger.warning("Validation skill not found: %s — skipping", skill_name)
        return True, "skill not found, skipped", 0.0

    # Build the validation prompt with the skill's cross-reference procedure.
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
        prompt,
        model=DESIGN_VALIDATOR_MODEL,
        slug=slug,
        phase=f"validation-step-{step_number}",
    )
    if failure_reason:
        return False, failure_reason, cost

    # Save the cross-reference report.
    try:
        save_cross_reference_report(slug, step_number, step_name, output)
    except OSError as exc:
        logger.warning("Failed to save cross-reference report: %s", exc)

    # Parse verdict from output.
    upper = output.strip().upper()
    if "FAIL" in upper.split("\n")[-1]:
        reason = output.strip().split("\n")[-1]
        return False, reason, cost
    if "WARN" in upper.split("\n")[-1]:
        reason = output.strip().split("\n")[-1]
        return True, reason, cost  # WARN is advisory, not blocking
    return True, "", cost


def _run_five_whys_analysis(item_path: str, item_type: str = "analysis",
                            clause_register: str = "", slug: str = "") -> dict[str, str | int | float | bool]:
    """Spawn Claude to run a 5-Whys analysis on any backlog item.

    Returns a dict with a "failed" key (bool). When failed=True, raw_output is
    empty and failure_reason contains the error description. Callers must check
    "failed" before treating raw_output as valid analysis.

    When clause_register is provided, uses the clause-referenced prompt format
    that requires C<n> references in each Why. Falls back to the original
    prompt when no clause register is available.
    """
    content = _read_file_content(item_path)
    if clause_register:
        prompt = FIVE_WHYS_WITH_CLAUSES_PROMPT.format(
            item_content=content, item_type=item_type, clause_register=clause_register,
        )
    else:
        prompt = FIVE_WHYS_PROMPT.format(item_content=content, item_type=item_type)
    output, cost, failure_reason = _call_llm(prompt, slug=slug, phase="intake-five-whys")
    if failure_reason:
        return {
            "failed": True,
            "failure_reason": failure_reason,
            "clarity": INTAKE_CLARITY_THRESHOLD,
            "raw_output": "",
            "total_cost_usd": 0.0,
        }
    clarity = _parse_clarity_score(output)
    return {"failed": False, "failure_reason": "", "clarity": clarity, "raw_output": output, "total_cost_usd": cost}


def _run_intake_analysis(
    item_path: str,
    item_slug: str,
    item_type: str,
) -> tuple[str, str, float, bool]:
    """Run clause extraction, 5 Whys, and skill-based validation for an item.

    Returns (clause_register_path, five_whys_path, total_cost, quota_exhausted).
    Paths are empty strings if the corresponding step failed or was skipped.
    """
    total_cost: float = 0.0
    quota_exhausted = False
    clause_register_path = ""
    five_whys_path = ""
    clause_register_content = ""

    # Step 1: Clause extraction.
    logger.info("Running clause extraction for %s...", item_slug)
    clause_result = _run_clause_extraction(item_path, slug=item_slug)
    if clause_result.get("failed"):
        logger.warning("Clause extraction failed for %s: %s", item_slug, clause_result.get("failure_reason", ""))
    else:
        total_cost += float(clause_result.get("total_cost_usd", 0.0))
        clause_register_content = str(clause_result["raw_output"])
        clause_register_path = _save_clause_register(item_slug, clause_register_content)

        # Validate clause extraction with skill.
        raw_content = _read_file_content(item_path)
        valid, reason, val_cost = _validate_with_skill(
            "clause-extraction-validation.md",
            {"Raw Backlog Item": raw_content},
            clause_register_content,
            slug=item_slug,
            step_number=1,
            step_name="clause-extraction",
        )
        total_cost += val_cost
        if valid:
            logger.info("Step 1 (clause extraction) validation PASSED for %s", item_slug)
        else:
            logger.warning("Step 1 (clause extraction) validation issue for %s: %s", item_slug, reason)

    # Step 2: 5 Whys analysis (skip if already present).
    if not _has_five_whys(item_path):
        logger.info("Running 5 Whys analysis for %s...", item_slug)
        whys_result = _run_five_whys_analysis(
            item_path, item_type=item_type,
            clause_register=clause_register_content, slug=item_slug,
        )
        whys_check = str(whys_result["raw_output"]) or str(whys_result.get("failure_reason", ""))
        if detect_quota_exhaustion(whys_check):
            return clause_register_path, "", total_cost, True
        if whys_result.get("failed"):
            _report_intake_error(
                f"[INTAKE] 5 Whys analysis failed for {item_slug}: {whys_result.get('failure_reason', '')}"
            )
        else:
            total_cost += float(whys_result.get("total_cost_usd", 0.0))
            whys_content = str(whys_result["raw_output"])
            five_whys_path = _save_five_whys(item_slug, whys_content)
            # Keep appending summary to item file for backward compatibility.
            _append_analysis_to_item(item_path, whys_content)

            # Validate 5 Whys with skill.
            if clause_register_content:
                valid, reason, val_cost = _validate_with_skill(
                    "five-whys-validation.md",
                    {"Clause Register": clause_register_content},
                    whys_content,
                    slug=item_slug,
                    step_number=2,
                    step_name="five-whys",
                )
                total_cost += val_cost
                if valid:
                    logger.info("Step 2 (5 Whys) validation PASSED for %s", item_slug)
                else:
                    logger.warning("Step 2 (5 Whys) validation issue for %s: %s", item_slug, reason)
            else:
                # Fallback: use legacy validation when no clause register available.
                valid, reason, val_cost = _validate_five_whys(item_path)
                total_cost += val_cost
                if valid:
                    logger.info("5 Whys validation PASSED for %s (legacy)", item_slug)
                else:
                    logger.warning("5 Whys validation FAILED for %s: %s", item_slug, reason)
    else:
        logger.info("5 Whys already present for %s", item_slug)
        # Try to load existing 5 Whys from workspace if available.
        from langgraph_pipeline.shared.paths import workspace_path
        existing_whys = workspace_path(item_slug) / "five-whys.md"
        if existing_whys.exists():
            five_whys_path = str(existing_whys)

    return clause_register_path, five_whys_path, total_cost, quota_exhausted


# ─── Node ─────────────────────────────────────────────────────────────────────


def intake_analyze(state: PipelineState) -> dict:
    """LangGraph node: analyze a backlog item before plan creation.

    Short-circuits when plan_path is already set (in-progress plan resumption),
    since the item has already been analyzed in a prior pipeline run.

    For defects, spawns Claude to verify symptoms are still reproducible.
    For analyses, spawns Claude to run a 5-Whys root-cause classification.
    For features, passes through without spawning a Claude session.

    Updates the in-graph intake counters (intake_count_defects / features).
    The disk-persisted throttle and RAG dedup are checked but non-blocking
    for items that already exist in the backlog.
    """
    item_path: str = state.get("item_path", "")
    item_type: str = state.get("item_type", "feature")
    item_slug: str = state.get("item_slug", "")
    plan_path: Optional[str] = state.get("plan_path")

    # Short-circuit: plan already exists (in-progress plan resumption).
    if plan_path:
        return {}

    # Safety gate: block when intake is throttled, waiting for the window to clear.
    if _check_throttle(item_type):
        print(
            f"[intake_analyze] Throttle limit reached for {item_type} "
            "— pausing intake. Waiting for window to clear."
        )
        shutdown_event = get_shutdown_event()
        while True:
            shutdown_event.wait(THROTTLE_WAIT_INTERVAL_SECONDS)
            if shutdown_event.is_set():
                return {}
            if not _check_throttle(item_type):
                print(
                    f"[intake_analyze] Throttle cleared for {item_type} — resuming."
                )
                break

    # Safety gate: check for semantic duplicates.
    if item_slug and _check_rag_dedup(item_slug):
        print(f"[intake_analyze] Possible duplicate found for: {item_slug}")

    # Type-specific analysis.
    state_updates: dict = {}
    total_cost_usd: float = 0.0

    if item_type == "defect" and item_path:
        # Defect symptom verification.
        result = _verify_defect_symptoms(item_path)
        symptom_check = str(result["raw_output"]) or str(result.get("failure_reason", ""))
        if detect_quota_exhaustion(symptom_check):
            return {"quota_exhausted": True}
        if result.get("failed"):
            _report_intake_error(
                f"[INTAKE] defect symptom check failed for {item_slug}: {result.get('failure_reason', '')}"
            )
        clarity = result["clarity"]
        reproducible = result["reproducible"]
        total_cost_usd = float(result.get("total_cost_usd", 0.0))

        if clarity < INTAKE_CLARITY_THRESHOLD:
            print(
                f"[intake_analyze] Low clarity score {clarity} for defect: {item_slug}"
            )

        if reproducible == "no":
            print(
                f"[intake_analyze] Defect symptoms not reproducible: {item_slug}"
            )

        # Clause extraction + 5 Whys + validation.
        clause_path, whys_path, analysis_cost, analysis_quota = _run_intake_analysis(
            item_path, item_slug, item_type="defect",
        )
        total_cost_usd += analysis_cost
        if analysis_quota:
            return {"quota_exhausted": True}
        if clause_path:
            state_updates["clause_register_path"] = clause_path
        if whys_path:
            state_updates["five_whys_path"] = whys_path

        state_updates["intake_count_defects"] = (
            state.get("intake_count_defects", 0) + 1
        )

    elif item_type == "feature" and item_path:
        # Clause extraction + 5 Whys + validation.
        clause_path, whys_path, analysis_cost, analysis_quota = _run_intake_analysis(
            item_path, item_slug, item_type="feature",
        )
        total_cost_usd += analysis_cost
        if analysis_quota:
            return {"quota_exhausted": True}
        if clause_path:
            state_updates["clause_register_path"] = clause_path
        if whys_path:
            state_updates["five_whys_path"] = whys_path

        state_updates["intake_count_features"] = (
            state.get("intake_count_features", 0) + 1
        )

    elif item_type == "analysis" and item_path:
        # Clause extraction + 5 Whys + validation.
        clause_path, whys_path, analysis_cost, analysis_quota = _run_intake_analysis(
            item_path, item_slug, item_type="analysis",
        )
        total_cost_usd += analysis_cost
        if analysis_quota:
            return {"quota_exhausted": True}
        if clause_path:
            state_updates["clause_register_path"] = clause_path
        if whys_path:
            state_updates["five_whys_path"] = whys_path

        state_updates["intake_count_features"] = (
            state.get("intake_count_features", 0) + 1
        )

    # Record this intake for throttle tracking.
    _record_intake(item_type)

    add_trace_metadata({
        "node_name": "intake_analyze",
        "graph_level": "pipeline",
        "item_slug": item_slug,
        "item_type": item_type,
        "total_cost_usd": total_cost_usd,
    })

    prior_cost = float(state.get("session_cost_usd") or 0.0)
    state_updates["session_cost_usd"] = prior_cost + total_cost_usd
    return state_updates
