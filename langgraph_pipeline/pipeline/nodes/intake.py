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

The throttle file lives on disk (.claude/plans/.backlog-creation-throttle.json)
so it survives LangGraph checkpoint restarts and process crashes.
"""

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from langgraph_pipeline.pipeline.state import PipelineState
from langgraph_pipeline.shared.langsmith import add_trace_metadata
from langgraph_pipeline.shared.quota import detect_quota_exhaustion
from langgraph_pipeline.shared.shutdown import get_shutdown_event

# ─── Constants ────────────────────────────────────────────────────────────────

THROTTLE_FILE_PATH = ".claude/plans/.backlog-creation-throttle.json"
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
INTAKE_ANALYSIS_TIMEOUT_SECONDS = 120
INTAKE_MODEL = "claude-haiku-4-5-20251001"  # Haiku sufficient for classification tasks

# Similarity threshold for RAG deduplication (0.0 – 1.0).
RAG_SIMILARITY_THRESHOLD = 0.75

# Regex patterns for parsing Claude output fields.
_CLARITY_PATTERN = re.compile(r"Clarity:\s*([1-5])", re.IGNORECASE)
_REPRODUCIBLE_PATTERN = re.compile(r"Reproducible:\s*(yes|no|unclear)", re.IGNORECASE)

# ─── Prompt templates ─────────────────────────────────────────────────────────

DEFECT_SYMPTOM_PROMPT = (
    "You are analyzing a defect backlog item to verify symptoms are still present.\n\n"
    "Read the defect backlog item at: {item_path}\n\n"
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
    "Read the backlog item at: {item_path}\n\n"
    "Does this item already contain a 5 Whys analysis (5 numbered Why "
    "questions with answers and a Root Need)?\n\n"
    "Respond with ONLY one word: YES or NO"
)

CHECK_HAS_ACCEPTANCE_CHECKLIST_PROMPT = (
    "Read the design document at: {design_doc_path}\n\n"
    "Does this design document contain acceptance criteria written as a "
    "checklist of specific YES/NO questions (e.g. 'Does X work? YES = pass, "
    "NO = fail')?\n\n"
    "Respond with ONLY one word: YES or NO"
)

DESIGN_VALIDATOR_MODEL = "claude-opus-4-6"
DESIGN_VALIDATOR_TIMEOUT_SECONDS = 60

VALIDATE_FIVE_WHYS_PROMPT = (
    "Read the backlog item at: {item_path}\n\n"
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
    "Read the design document at: {design_doc_path}\n\n"
    "Read the original backlog item at: {item_path}\n\n"
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
    "Read the backlog item at: {item_path}\n\n"
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


def _invoke_claude(prompt: str, timeout: int = INTAKE_ANALYSIS_TIMEOUT_SECONDS) -> tuple[str, float]:
    """Invoke Claude CLI with --print and return (text, total_cost_usd).

    Uses --output-format json so cost data is available in the response.
    Returns ("", 0.0) on failure. On non-zero exit code, returns stderr
    (not stdout) so that quota/rate-limit detection does not false-positive
    on keywords that appear in Claude's response text.
    """
    try:
        result = subprocess.run(
            ["claude", "--model", INTAKE_MODEL, "--print", prompt, "--output-format", "json"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0 and result.stdout:
            data = json.loads(result.stdout)
            text = data.get("result", "").strip()
            cost = float(data.get("total_cost_usd", 0.0))
            return text, cost
        # Return stderr on failure — callers check this for quota/rate-limit
        # signals. Returning stdout here caused false positives when Claude's
        # response text contained limit-related keywords.
        return result.stderr or "", 0.0
    except (subprocess.TimeoutExpired, OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return "", 0.0


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


def _verify_defect_symptoms(item_path: str) -> dict[str, str | int | float]:
    """Spawn Claude to verify defect symptoms and return parsed result fields."""
    prompt = DEFECT_SYMPTOM_PROMPT.format(item_path=item_path)
    output, cost = _invoke_claude(prompt)
    clarity = _parse_clarity_score(output)

    reproducible_match = _REPRODUCIBLE_PATTERN.search(output)
    reproducible = reproducible_match.group(1).lower() if reproducible_match else "unclear"

    return {"reproducible": reproducible, "clarity": clarity, "raw_output": output, "total_cost_usd": cost}


def _invoke_claude_opus(prompt: str, timeout: int = DESIGN_VALIDATOR_TIMEOUT_SECONDS) -> tuple[str, float]:
    """Invoke Claude CLI with Opus model for quality validation checks."""
    try:
        result = subprocess.run(
            ["claude", "--model", DESIGN_VALIDATOR_MODEL, "--print", prompt,
             "--output-format", "json", "--dangerously-skip-permissions",
             "--permission-mode", "acceptEdits"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0 and result.stdout:
            data = json.loads(result.stdout)
            text = data.get("result", "").strip()
            cost = float(data.get("total_cost_usd", 0.0))
            return text, cost
        return result.stderr or "", 0.0
    except (subprocess.TimeoutExpired, OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return "", 0.0


def _has_five_whys(item_path: str) -> bool:
    """Use Haiku to check if the backlog item already contains a 5 Whys analysis."""
    prompt = CHECK_HAS_FIVE_WHYS_PROMPT.format(item_path=item_path)
    output, _cost = _invoke_claude(prompt, timeout=30)
    return output.strip().upper().startswith("YES")


def _validate_five_whys(item_path: str) -> tuple[bool, str]:
    """Use Opus to validate 5 Whys quality — no unjustified assumptions, conclusion matches request."""
    prompt = VALIDATE_FIVE_WHYS_PROMPT.format(item_path=item_path)
    output, _cost = _invoke_claude_opus(prompt)
    valid = output.strip().upper().startswith("VALID")
    reason = output.strip().split("\n", 1)[1].strip() if "\n" in output.strip() else ""
    return valid, reason


def _validate_design(design_doc_path: str, item_path: str) -> tuple[bool, str]:
    """Use Opus to validate design — has checklist, matches request, no unjustified assumptions."""
    prompt = VALIDATE_DESIGN_PROMPT.format(design_doc_path=design_doc_path, item_path=item_path)
    output, _cost = _invoke_claude_opus(prompt)
    valid = output.strip().upper().startswith("VALID")
    reason = output.strip().split("\n", 1)[1].strip() if "\n" in output.strip() else ""
    return valid, reason


def _has_acceptance_checklist(design_doc_path: str) -> bool:
    """Use Haiku to check if the design doc contains YES/NO acceptance criteria."""
    prompt = CHECK_HAS_ACCEPTANCE_CHECKLIST_PROMPT.format(design_doc_path=design_doc_path)
    output, _cost = _invoke_claude(prompt, timeout=30)
    return output.strip().upper().startswith("YES")


def _run_five_whys_analysis(item_path: str, item_type: str = "analysis") -> dict[str, str | int | float]:
    """Spawn Claude to run a 5-Whys analysis on any backlog item."""
    prompt = FIVE_WHYS_PROMPT.format(item_path=item_path, item_type=item_type)
    output, cost = _invoke_claude(prompt)
    clarity = _parse_clarity_score(output)

    return {"clarity": clarity, "raw_output": output, "total_cost_usd": cost}


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
        # Step 1: Verify symptoms are still reproducible.
        result = _verify_defect_symptoms(item_path)
        if detect_quota_exhaustion(str(result["raw_output"])):
            return {"quota_exhausted": True}
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

        # Step 2: 5 Whys to understand root cause before planning (skip if already present).
        if not _has_five_whys(item_path):
            whys_result = _run_five_whys_analysis(item_path, item_type="defect")
            if detect_quota_exhaustion(str(whys_result["raw_output"])):
                return {"quota_exhausted": True}
            total_cost_usd += float(whys_result.get("total_cost_usd", 0.0))
        else:
            print(f"[intake_analyze] 5 Whys already present for defect: {item_slug}")

        # Step 3: Validate 5 Whys quality with Opus.
        valid, reason = _validate_five_whys(item_path)
        if not valid:
            print(f"[intake_analyze] WARNING: 5 Whys validation failed for {item_slug}: {reason}")

        state_updates["intake_count_defects"] = (
            state.get("intake_count_defects", 0) + 1
        )

    elif item_type == "feature" and item_path:
        # 5 Whys to understand the root need (skip if already present).
        if not _has_five_whys(item_path):
            result = _run_five_whys_analysis(item_path, item_type="feature")
            if detect_quota_exhaustion(str(result["raw_output"])):
                return {"quota_exhausted": True}
            clarity = result["clarity"]
            total_cost_usd = float(result.get("total_cost_usd", 0.0))

            if clarity < INTAKE_CLARITY_THRESHOLD:
                print(
                    f"[intake_analyze] Low clarity score {clarity} for feature: {item_slug}"
                )
        else:
            print(f"[intake_analyze] 5 Whys already present for feature: {item_slug}")

        # Validate 5 Whys quality with Opus.
        valid, reason = _validate_five_whys(item_path)
        if not valid:
            print(f"[intake_analyze] WARNING: 5 Whys validation failed for {item_slug}: {reason}")

        state_updates["intake_count_features"] = (
            state.get("intake_count_features", 0) + 1
        )

    elif item_type == "analysis" and item_path:
        if not _has_five_whys(item_path):
            result = _run_five_whys_analysis(item_path, item_type="analysis")
            if detect_quota_exhaustion(str(result["raw_output"])):
                return {"quota_exhausted": True}
            clarity = result["clarity"]
            total_cost_usd = float(result.get("total_cost_usd", 0.0))

            if clarity < INTAKE_CLARITY_THRESHOLD:
                print(
                    f"[intake_analyze] Low clarity score {clarity} for analysis: {item_slug}"
                )
        else:
            print(f"[intake_analyze] 5 Whys already present for analysis: {item_slug}")

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

    return state_updates
