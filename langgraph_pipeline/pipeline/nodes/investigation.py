# langgraph_pipeline/pipeline/nodes/investigation.py
# run_investigation and process_investigation LangGraph nodes.
# Design: docs/plans/2026-04-02-82-investigation-workflow-with-slack-proposals-design.md

"""Investigation nodes for the pipeline StateGraph.

Node sequence for investigation items:
  intake_analyze -> run_investigation -> process_investigation -> archive | END
"""

import json
import logging
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from langgraph_pipeline.investigation.proposals import (
    Proposal,
    ProposalSet,
    load_proposals,
    save_proposals,
)
from langgraph_pipeline.pipeline.state import PipelineState
from langgraph_pipeline.shared.paths import workspace_path

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

INVESTIGATION_MODEL = "claude-opus-4-6"
INVESTIGATION_TIMEOUT_SECONDS = 1200  # 20 minutes; investigation can be lengthy

# Tools the investigation node grants Claude to explore the codebase.
INVESTIGATION_ALLOWED_TOOLS = ["Read", "Grep", "Glob", "Bash"]

CLAUDE_BINARY = "claude"

# Regex to extract the first JSON array from Claude's output (may be fenced).
_JSON_ARRAY_PATTERN = re.compile(r"\[.*?\]", re.DOTALL)

# ─── Prompt template ─────────────────────────────────────────────────────────

INVESTIGATION_PROMPT = (
    "You are a senior software engineer conducting a systematic root-cause investigation.\n\n"
    "## Item Under Investigation\n\n"
    "---\n{item_content}\n---\n\n"
    "{clause_section}"
    "{five_whys_section}"
    "## Your Task\n\n"
    "Investigate the codebase thoroughly to identify the underlying causes and "
    "possible improvements. Use your tools (Read, Grep, Glob, Bash) to:\n"
    "1. Read relevant source files, logs, data, and traces referenced in the item.\n"
    "2. Trace execution paths to pinpoint defective logic or missing features.\n"
    "3. Gather concrete evidence: file paths, line numbers, variable names, log entries.\n\n"
    "## Required Output\n\n"
    "After your investigation, output ONLY a JSON array of proposals. "
    "Each proposal must have exactly these fields:\n"
    "  - type: \"defect\" or \"enhancement\"\n"
    "  - title: short imperative title (one line)\n"
    "  - description: detailed description with evidence citations "
    "(file:line references, log excerpts, etc.)\n"
    "  - severity: \"critical\", \"high\", \"medium\", or \"low\"\n\n"
    "Example format:\n"
    "[\n"
    "  {{\n"
    "    \"type\": \"defect\",\n"
    "    \"title\": \"Null pointer in archival node\",\n"
    "    \"description\": \"archival.py:42 dereferences item.slug without None check.\",\n"
    "    \"severity\": \"high\"\n"
    "  }}\n"
    "]\n\n"
    "IMPORTANT: Output ONLY the JSON array. Do not include any preamble, "
    "explanation, or markdown outside the JSON array itself."
)

CLAUSE_SECTION_TEMPLATE = (
    "## Clause Register (structured requirements)\n\n"
    "---\n{clause_content}\n---\n\n"
)

FIVE_WHYS_SECTION_TEMPLATE = (
    "## Five Whys Analysis\n\n"
    "---\n{five_whys_content}\n---\n\n"
)


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _workspace_dir(item_slug: str) -> Path:
    """Return the workspace directory Path for the given item slug."""
    return workspace_path(item_slug)


def _build_investigation_command(prompt: str) -> list[str]:
    """Build the Claude CLI command for investigation with planner-style permissions."""
    sandbox_enabled = (
        os.environ.get("ORCHESTRATOR_SANDBOX_ENABLED", "true").lower() != "false"
    )
    cmd = [CLAUDE_BINARY]
    cmd += ["--dangerously-skip-permissions"]
    cmd += ["--permission-mode", "acceptEdits"]
    if sandbox_enabled:
        cmd += ["--allowedTools"] + INVESTIGATION_ALLOWED_TOOLS
        cmd += ["--add-dir", os.getcwd()]
    cmd += ["--model", INVESTIGATION_MODEL]
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
            timeout=INVESTIGATION_TIMEOUT_SECONDS,
            env=child_env,
            cwd=os.getcwd(),
        )
        return result.returncode, result.stdout or "", result.stderr or ""
    except subprocess.TimeoutExpired:
        return -1, "", "Investigation subprocess timed out"
    except (OSError, subprocess.SubprocessError) as exc:
        return -1, "", str(exc)


def _read_file_optional(path: Optional[str]) -> Optional[str]:
    """Read a file and return its contents, or None if path is missing or unreadable."""
    if not path:
        return None
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return None


def _build_prompt(
    item_content: str,
    clause_content: Optional[str],
    five_whys_content: Optional[str],
) -> str:
    """Assemble the investigation prompt from content fragments."""
    clause_section = (
        CLAUSE_SECTION_TEMPLATE.format(clause_content=clause_content)
        if clause_content
        else ""
    )
    five_whys_section = (
        FIVE_WHYS_SECTION_TEMPLATE.format(five_whys_content=five_whys_content)
        if five_whys_content
        else ""
    )
    return INVESTIGATION_PROMPT.format(
        item_content=item_content,
        clause_section=clause_section,
        five_whys_section=five_whys_section,
    )


def _extract_text_from_json_output(stdout: str) -> tuple[str, float, int, int]:
    """Parse the Claude CLI JSON response envelope.

    Returns (result_text, cost_usd, input_tokens, output_tokens).
    """
    try:
        data = json.loads(stdout)
        text = data.get("result", "").strip()
        cost = float(data.get("total_cost_usd", 0.0))
        usage = data.get("usage", {})
        tok_in = int(usage.get("input_tokens", 0))
        tok_out = int(usage.get("output_tokens", 0))
        return text, cost, tok_in, tok_out
    except (json.JSONDecodeError, ValueError, TypeError):
        return "", 0.0, 0, 0


def _parse_proposals_from_output(text: str) -> list[dict]:
    """Extract the JSON array of proposals from Claude's output text.

    Raises ValueError if no valid JSON array is found.
    """
    match = _JSON_ARRAY_PATTERN.search(text)
    if not match:
        raise ValueError(
            f"No JSON array found in investigation output. Output preview: {text[:300]!r}"
        )
    raw_array = match.group(0)
    try:
        proposals_raw = json.loads(raw_array)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Failed to parse proposals JSON array: {exc}. Raw: {raw_array[:300]!r}"
        ) from exc
    if not isinstance(proposals_raw, list):
        raise ValueError(f"Expected a JSON array, got {type(proposals_raw).__name__}")
    return proposals_raw


def _build_proposal_set(slug: str, proposals_raw: list[dict]) -> ProposalSet:
    """Construct a ProposalSet from a list of raw proposal dicts from Claude."""
    proposals: list[Proposal] = []
    for index, raw in enumerate(proposals_raw, start=1):
        proposal = Proposal(
            number=index,
            proposal_type=raw["type"],
            title=raw["title"],
            description=raw["description"],
            severity=raw["severity"],
        )
        proposals.append(proposal)
    generated_at = datetime.now(timezone.utc).isoformat()
    return ProposalSet(slug=slug, generated_at=generated_at, proposals=proposals)


# ─── Nodes ────────────────────────────────────────────────────────────────────


def run_investigation(state: PipelineState) -> dict:
    """LangGraph node: run Claude-powered investigation and produce proposals.

    Idempotent: returns {} immediately if proposals.yaml already exists in
    the workspace. Otherwise spawns Claude Opus with investigation tools,
    parses the JSON array of proposals from the output, and persists them
    to proposals.yaml.

    Raises RuntimeError on subprocess failure and ValueError on parse failure,
    so the supervisor can handle the error and stop the pipeline cycle.
    """
    item_slug: str = state.get("item_slug", "")
    item_path: str = state.get("item_path", "")
    clause_register_path: Optional[str] = state.get("clause_register_path")
    five_whys_path: Optional[str] = state.get("five_whys_path")

    ws_dir = _workspace_dir(item_slug)

    # Idempotency: skip if proposals already exist from a prior run.
    if load_proposals(ws_dir) is not None:
        logger.info(
            "[run_investigation] proposals.yaml already exists — skipping item=%s", item_slug
        )
        return {}

    logger.info("[run_investigation] starting investigation for item=%s", item_slug)

    # Read input artifacts.
    item_content = _read_file_optional(item_path) or "(item content unavailable)"
    clause_content = _read_file_optional(clause_register_path)
    five_whys_content = _read_file_optional(five_whys_path)

    # Build and run the Claude subprocess.
    prompt = _build_prompt(item_content, clause_content, five_whys_content)
    cmd = _build_investigation_command(prompt)
    exit_code, stdout, stderr = _run_subprocess(cmd)

    if exit_code != 0:
        raise RuntimeError(
            f"Investigation Claude subprocess failed for item={item_slug} "
            f"with exit_code={exit_code}: {stderr[:500]}"
        )

    # Extract text and parse proposals.
    text, cost_usd, tok_in, tok_out = _extract_text_from_json_output(stdout)
    logger.info(
        "[run_investigation] Claude returned %d chars, cost=$%.4f, "
        "tokens_in=%d tokens_out=%d item=%s",
        len(text), cost_usd, tok_in, tok_out, item_slug,
    )

    proposals_raw = _parse_proposals_from_output(text)
    proposal_set = _build_proposal_set(item_slug, proposals_raw)

    # Persist proposals to workspace.
    save_proposals(proposal_set, ws_dir)
    logger.info(
        "[run_investigation] saved %d proposals for item=%s",
        len(proposal_set.proposals),
        item_slug,
    )

    return {}


def process_investigation(state: PipelineState) -> dict:
    """LangGraph node: process Slack approval and file accepted proposals.

    Placeholder — returns state unchanged.  Full implementation (polling
    the Slack thread, parsing the user's response, and filing accepted
    proposals as backlog items) is delivered in task 3.x.
    """
    item_slug = state.get("item_slug", "")
    logger.info("[process_investigation] placeholder — item=%s", item_slug)
    return {}
