# langgraph_pipeline/pipeline/nodes/verification.py
# verify_symptoms LangGraph node: run post-fix defect verification, parse PASS/FAIL.
# Design: docs/plans/2026-02-26-04-pipeline-graph-nodes-design.md

"""verify_symptoms node for the pipeline StateGraph.

After execute_plan runs the plan that fixes a defect, verify_symptoms
spawns Claude to check whether the original defect symptoms have been
resolved.  It parses PASS or FAIL from Claude's response, appends a
VerificationRecord to verification_history, and increments
verification_cycle so the verify_result conditional edge can route
accordingly.
"""

import re
import subprocess
from datetime import datetime, timezone
from typing import Optional

from langgraph_pipeline.pipeline.state import PipelineState, VerificationRecord

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


def _invoke_claude(prompt: str) -> str:
    """Invoke the Claude CLI with --print and return combined stdout.

    Returns empty string on timeout, OS errors, or subprocess failures.
    """
    try:
        result = subprocess.run(
            ["claude", "--print", prompt],
            capture_output=True,
            text=True,
            timeout=VERIFICATION_TIMEOUT_SECONDS,
        )
        return result.stdout or ""
    except (subprocess.TimeoutExpired, OSError, subprocess.SubprocessError):
        return ""


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


def verify_symptoms(state: PipelineState) -> dict:
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
        print(f"[verify_symptoms] No item_path in state for {item_slug}; skipping.")
        record = _build_verification_record("FAIL", "No item_path available for verification.")
        return {
            "verification_history": [record],
            "verification_cycle": cycle + 1,
        }

    print(f"[verify_symptoms] Verifying defect symptoms for {item_slug} (cycle {cycle + 1})")

    prompt = VERIFICATION_PROMPT.format(item_path=item_path)
    output: str = _invoke_claude(prompt)

    outcome: str = _parse_verification_outcome(output)
    notes: str = output.strip() if output else "No output from verification."

    record = _build_verification_record(outcome, notes)

    print(f"[verify_symptoms] Verification outcome for {item_slug}: {outcome}")

    return {
        "verification_history": [record],
        "verification_cycle": cycle + 1,
    }
