# langgraph_pipeline/pipeline/nodes/verification.py
# verify_fix LangGraph node: run post-fix defect verification, parse PASS/FAIL.
# Design: docs/plans/2026-02-26-04-pipeline-graph-nodes-design.md

"""verify_fix node for the pipeline StateGraph.

After execute_plan runs the plan that fixes a defect, verify_fix
spawns Claude to check whether the original defect symptoms have been
resolved.  It parses PASS or FAIL from Claude's response, appends a
VerificationRecord to verification_history, and increments
verification_cycle so the verify_result conditional edge can route
accordingly.
"""

import json
import re
import subprocess
from datetime import datetime, timezone
from typing import Optional

from langgraph_pipeline.pipeline.state import PipelineState, VerificationRecord
from langgraph_pipeline.shared.langsmith import add_trace_metadata

# ─── Constants ────────────────────────────────────────────────────────────────

VERIFICATION_TIMEOUT_SECONDS = 300
VERIFICATION_NOTES_MAX_LENGTH = 500

# Patterns for detecting PASS/FAIL in Claude's output.
_PASS_PATTERN = re.compile(r"\bPASS\b", re.IGNORECASE)
_FAIL_PATTERN = re.compile(r"\bFAIL\b", re.IGNORECASE)

# ─── Prompt template ─────────────────────────────────────────────────────────

VERIFICATION_PROMPT = (
    "You are verifying whether a defect has been fixed.\n\n"
    "Read the defect backlog item at: {item_path}\n\n"
    "Your task:\n"
    "1. Read and understand the original reported symptoms.\n"
    "2. Read the code changes that were made to fix the defect.\n"
    "3. Run the relevant tests (if available) to check for regressions.\n"
    "4. Determine whether the symptoms described in the backlog item are now resolved.\n\n"
    "Respond in this exact format (include the word PASS or FAIL in capital letters):\n\n"
    "Result: PASS   (if the defect symptoms are resolved)\n"
    "  OR\n"
    "Result: FAIL   (if the defect symptoms remain or new issues were introduced)\n\n"
    "Notes: <one or two sentences summarizing what you checked and what you found>"
)

# ─── Helpers ──────────────────────────────────────────────────────────────────


def _invoke_claude(prompt: str) -> tuple[str, float]:
    """Invoke the Claude CLI with --print and return (text, total_cost_usd).

    Uses --output-format json so cost data is available in the response.
    Returns ("", 0.0) on timeout, OS errors, or subprocess failures.
    """
    try:
        result = subprocess.run(
            ["claude", "--print", prompt, "--output-format", "json"],
            capture_output=True,
            text=True,
            timeout=VERIFICATION_TIMEOUT_SECONDS,
        )
        if result.returncode == 0 and result.stdout:
            data = json.loads(result.stdout)
            text = data.get("result", "").strip()
            cost = float(data.get("total_cost_usd", 0.0))
            return text, cost
        return result.stdout or "", 0.0
    except (subprocess.TimeoutExpired, OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return "", 0.0


def _parse_verification_outcome(output: str) -> str:
    """Extract PASS or FAIL from Claude's verification output.

    Returns "PASS" when Claude explicitly states the defect is resolved,
    "FAIL" otherwise (including when the output cannot be parsed).
    """
    if _PASS_PATTERN.search(output):
        return "PASS"
    return "FAIL"


def _build_verification_record(outcome: str, notes: str) -> VerificationRecord:
    """Build a VerificationRecord dict from outcome and raw notes."""
    return {
        "outcome": outcome,  # type: ignore[typeddict-item]
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "notes": notes[:VERIFICATION_NOTES_MAX_LENGTH],
    }


# ─── Node ─────────────────────────────────────────────────────────────────────


def verify_fix(state: PipelineState) -> dict:
    """LangGraph node: verify that a defect's symptoms have been resolved.

    Spawns Claude to inspect the backlog item and check whether the
    reported symptoms are still present after the plan was executed.
    Appends a VerificationRecord to verification_history (via the
    Annotated[list, operator.add] merge strategy) and increments
    verification_cycle.

    Returns partial state updates:
      verification_history: single-element list to be merged (appended).
      verification_cycle: current cycle count incremented by 1.
    """
    item_path: str = state.get("item_path", "")
    item_slug: str = state.get("item_slug", "")
    cycle: int = state.get("verification_cycle") or 0

    if not item_path:
        print(f"[verify_fix] No item_path in state for {item_slug}; skipping.")
        record = _build_verification_record("FAIL", "No item_path available for verification.")
        return {
            "verification_history": [record],
            "verification_cycle": cycle + 1,
        }

    print(f"[verify_fix] Verifying defect symptoms for {item_slug} (cycle {cycle + 1})")

    prompt = VERIFICATION_PROMPT.format(item_path=item_path)
    output, total_cost_usd = _invoke_claude(prompt)

    outcome: str = _parse_verification_outcome(output)
    notes: str = output.strip() if output else "No output from verification."

    record = _build_verification_record(outcome, notes)

    print(f"[verify_fix] Verification outcome for {item_slug}: {outcome}")

    # Build full traceability matrix if workspace artifacts exist.
    _build_traceability_matrix(item_slug)

    add_trace_metadata({
        "node_name": "verify_fix",
        "graph_level": "pipeline",
        "item_slug": item_slug,
        "item_type": "defect",
        "verification_cycle": cycle + 1,
        "outcome": outcome,
        "total_cost_usd": total_cost_usd,
    })

    prior_cost = float(state.get("session_cost_usd") or 0.0)
    return {
        "verification_history": [record],
        "verification_cycle": cycle + 1,
        "session_cost_usd": prior_cost + total_cost_usd,
    }


def _build_traceability_matrix(item_slug: str) -> Optional[str]:
    """Assemble the full traceability matrix from workspace artifacts.

    Reads clause register, requirements, and cross-reference reports from the
    workspace to produce the end-to-end traceability matrix:
        C -> UC/P/FR -> AC -> D -> T -> VF

    Saves the matrix to tmp/workspace/{slug}/traceability/traceability-matrix.md.
    Returns the file path on success, None if artifacts are missing.
    """
    import logging
    logger = logging.getLogger(__name__)

    from langgraph_pipeline.shared.paths import workspace_path

    ws = workspace_path(item_slug)
    clauses_path = ws / "clauses.md"
    requirements_path = ws / "requirements.md"
    validation_dir = ws / "validation"

    # All three core artifacts needed for the matrix.
    if not clauses_path.exists() or not requirements_path.exists():
        logger.info("Skipping traceability matrix for %s — missing clause register or requirements", item_slug)
        return None

    try:
        clauses = clauses_path.read_text(encoding="utf-8")
        requirements = requirements_path.read_text(encoding="utf-8")
    except OSError:
        return None

    # Collect cross-reference reports.
    xref_reports: list[str] = []
    if validation_dir.exists():
        for report_file in sorted(validation_dir.glob("step-*.md")):
            try:
                xref_reports.append(report_file.read_text(encoding="utf-8"))
            except OSError:
                continue

    # Build the matrix document.
    timestamp = datetime.now(tz=timezone.utc).isoformat()
    matrix_lines = [
        f"# Full Traceability Matrix: {item_slug}",
        f"",
        f"Generated: {timestamp}",
        f"",
        f"## Source Artifacts",
        f"",
        f"- Clause Register: {clauses_path}",
        f"- Requirements: {requirements_path}",
        f"- Cross-reference reports: {len(xref_reports)} found",
        f"",
        f"## Clause Register Summary",
        f"",
        clauses[:2000],  # First 2000 chars as summary
        f"",
        f"## Requirements Summary",
        f"",
        requirements[:2000],
        f"",
        f"## Cross-Reference Reports",
        f"",
    ]
    for i, report in enumerate(xref_reports, 1):
        matrix_lines.append(f"### Report {i}")
        matrix_lines.append(f"")
        matrix_lines.append(report[:3000])
        matrix_lines.append(f"")

    matrix_content = "\n".join(matrix_lines)

    # Save to workspace.
    traceability_dir = ws / "traceability"
    traceability_dir.mkdir(parents=True, exist_ok=True)
    matrix_path = traceability_dir / "traceability-matrix.md"
    try:
        matrix_path.write_text(matrix_content, encoding="utf-8")
        logger.info("Traceability matrix saved to %s", matrix_path)
        return str(matrix_path)
    except OSError as exc:
        logger.warning("Failed to save traceability matrix: %s", exc)
        return None
