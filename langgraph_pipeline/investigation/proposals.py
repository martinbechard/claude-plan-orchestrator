# langgraph_pipeline/investigation/proposals.py
# Proposal data model, persistence, and approval-response parsing for investigation workflow.
# Design: docs/plans/2026-04-02-82-investigation-workflow-with-slack-proposals-design.md

"""Proposal dataclasses, YAML persistence, and parse_approval_response for investigation items."""

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

import yaml

from langgraph_pipeline.shared.claude_cli import call_claude

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

PROPOSALS_FILENAME = "proposals.yaml"
NUMBERS_PATTERN = re.compile(r"^[\d,\s]+$")
ALL_EXCEPT_PATTERN = re.compile(r"^all\s+except\s+([\d,\s]+)$")

# Timeout in seconds for the LLM fallback call in parse_approval_response
LLM_FALLBACK_TIMEOUT_S = 60

# Model used for the LLM fallback when deterministic parsing fails
LLM_FALLBACK_MODEL = "haiku"


# ─── Data model ───────────────────────────────────────────────────────────────


@dataclass
class Proposal:
    """A single investigation proposal for a defect or enhancement.

    number is 1-based, matching the display order in the Slack message.
    status defaults to 'pending' until a human accepts or rejects it.
    filed_path is set after the proposal is filed as a backlog item.
    """

    number: int
    proposal_type: Literal["defect", "enhancement"]
    title: str
    description: str
    severity: Literal["critical", "high", "medium", "low"]
    status: Literal["pending", "accepted", "rejected"] = "pending"
    filed_path: Optional[str] = None


@dataclass
class ProposalSet:
    """The complete set of proposals generated for one investigation item.

    slug identifies the investigation item whose workspace holds proposals.yaml.
    generated_at is an ISO-8601 timestamp of when the proposals were created.
    slack_channel_id and slack_thread_ts are set after posting to Slack.
    reply_text is set when a human reply is detected in the Slack thread.
    status reflects overall approval disposition once all proposals are processed.
    """

    slug: str
    generated_at: str
    proposals: list[Proposal] = field(default_factory=list)
    status: Literal["pending", "approved", "rejected", "partial"] = "pending"
    slack_channel_id: Optional[str] = None
    slack_thread_ts: Optional[str] = None
    reply_text: Optional[str] = None


# ─── Persistence ──────────────────────────────────────────────────────────────


def _proposal_to_dict(proposal: Proposal) -> dict:
    """Convert a Proposal dataclass to a plain dict for YAML serialization."""
    return {
        "number": proposal.number,
        "proposal_type": proposal.proposal_type,
        "title": proposal.title,
        "description": proposal.description,
        "severity": proposal.severity,
        "status": proposal.status,
        "filed_path": proposal.filed_path,
    }


def _proposal_set_to_dict(proposal_set: ProposalSet) -> dict:
    """Convert a ProposalSet dataclass to a plain dict for YAML serialization."""
    return {
        "slug": proposal_set.slug,
        "generated_at": proposal_set.generated_at,
        "status": proposal_set.status,
        "slack_channel_id": proposal_set.slack_channel_id,
        "slack_thread_ts": proposal_set.slack_thread_ts,
        "reply_text": proposal_set.reply_text,
        "proposals": [_proposal_to_dict(p) for p in proposal_set.proposals],
    }


def _dict_to_proposal(data: dict) -> Proposal:
    """Reconstruct a Proposal dataclass from a plain dict."""
    return Proposal(
        number=data["number"],
        proposal_type=data["proposal_type"],
        title=data["title"],
        description=data["description"],
        severity=data["severity"],
        status=data.get("status", "pending"),
        filed_path=data.get("filed_path"),
    )


def _dict_to_proposal_set(data: dict) -> ProposalSet:
    """Reconstruct a ProposalSet dataclass from a plain dict."""
    proposals = [_dict_to_proposal(p) for p in data.get("proposals", [])]
    return ProposalSet(
        slug=data["slug"],
        generated_at=data["generated_at"],
        proposals=proposals,
        status=data.get("status", "pending"),
        slack_channel_id=data.get("slack_channel_id"),
        slack_thread_ts=data.get("slack_thread_ts"),
        reply_text=data.get("reply_text"),
    )


def save_proposals(proposal_set: ProposalSet, workspace_dir: Path) -> None:
    """Write proposal_set to proposals.yaml in workspace_dir using PyYAML safe_dump.

    Creates workspace_dir if it does not exist.
    """
    workspace_dir.mkdir(parents=True, exist_ok=True)
    proposals_path = workspace_dir / PROPOSALS_FILENAME
    data = _proposal_set_to_dict(proposal_set)
    with open(proposals_path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, default_flow_style=False, allow_unicode=True)
    logger.debug("Saved proposals to %s", proposals_path)


def load_proposals(workspace_dir: Path) -> Optional[ProposalSet]:
    """Read proposals.yaml from workspace_dir and reconstruct a ProposalSet.

    Returns None if proposals.yaml does not exist in workspace_dir.
    """
    proposals_path = workspace_dir / PROPOSALS_FILENAME
    if not proposals_path.exists():
        return None
    with open(proposals_path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return _dict_to_proposal_set(data)


# ─── Response parsing ─────────────────────────────────────────────────────────


def _parse_number_list(text: str, proposal_count: int) -> set[int]:
    """Parse a comma/space-separated list of numbers, filtering to valid range."""
    parts = re.split(r"[,\s]+", text.strip())
    result: set[int] = set()
    for part in parts:
        part = part.strip()
        if not part:
            continue
        try:
            n = int(part)
            if 1 <= n <= proposal_count:
                result.add(n)
        except ValueError:
            pass
    return result


def _llm_fallback(text: str, proposal_count: int) -> set[int]:
    """Call Claude Haiku to interpret a free-text approval response.

    Returns the set of accepted proposal numbers, or empty set on failure.
    """
    prompt = (
        f"A human was asked to approve or reject investigation proposals numbered "
        f"1 to {proposal_count}. Their reply was:\n\n{text}\n\n"
        f"Return ONLY a JSON array of accepted proposal numbers (e.g. [1, 3]). "
        f"If none are accepted, return []. Do not include any explanation."
    )
    result = call_claude(prompt, model=LLM_FALLBACK_MODEL, timeout=LLM_FALLBACK_TIMEOUT_S)
    if result.failure_reason:
        logger.warning(
            "LLM fallback failed for approval response parsing: failure_reason=%s",
            result.failure_reason,
        )
        return set()

    output = result.text.strip()
    # Extract a JSON array from the output
    match = re.search(r"\[.*?\]", output, re.DOTALL)
    if not match:
        logger.warning(
            "LLM fallback returned no JSON array: output=%r", output[:200]
        )
        return set()
    try:
        numbers = json.loads(match.group(0))
        return {n for n in numbers if isinstance(n, int) and 1 <= n <= proposal_count}
    except (json.JSONDecodeError, TypeError) as exc:
        logger.warning("LLM fallback JSON parse error: %s", exc)
        return set()


def parse_approval_response(text: str, proposal_count: int) -> set[int]:
    """Parse a human Slack reply into a set of accepted proposal numbers.

    Strategy chain (evaluated in order):
    1. "all" or "yes"  -> accept all proposals
    2. "none" or "no"  -> accept none
    3. Comma/space-separated numbers -> parse each, validate in 1..proposal_count
    4. "all except <numbers>" -> full set minus listed numbers
    5. LLM fallback via Claude Haiku -> return parsed set or empty set on failure

    Args:
        text: The human's reply text from Slack.
        proposal_count: Total number of proposals in the set.

    Returns:
        A set of accepted proposal numbers (1-based).
    """
    full_set = set(range(1, proposal_count + 1))
    normalized = text.strip().lower()

    # Strategy 1: wholesale accept
    if normalized in ("all", "yes"):
        return full_set

    # Strategy 2: wholesale reject
    if normalized in ("none", "no"):
        return set()

    # Strategy 3: comma/space-separated numbers
    if NUMBERS_PATTERN.match(normalized):
        return _parse_number_list(normalized, proposal_count)

    # Strategy 4: "all except ..." pattern
    match = ALL_EXCEPT_PATTERN.match(normalized)
    if match:
        excluded = _parse_number_list(match.group(1), proposal_count)
        return full_set - excluded

    # Strategy 5: LLM fallback
    return _llm_fallback(text, proposal_count)
