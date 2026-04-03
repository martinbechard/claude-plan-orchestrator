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
from langgraph_pipeline.shared.paths import DEFECT_DIR, FEATURE_DIR

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

PROPOSALS_FILENAME = "proposals.yaml"
NUMBERS_PATTERN = re.compile(r"^[\d,\s]+$")
ALL_EXCEPT_PATTERN = re.compile(r"^all\s+except\s+([\d,\s]+)$")

# Timeout in seconds for the LLM fallback call in parse_approval_response
LLM_FALLBACK_TIMEOUT_S = 60

# Model used for the LLM fallback when deterministic parsing fails
LLM_FALLBACK_MODEL = "haiku"

# Backlog filing constants
TITLE_SLUG_MAX_LEN = 60
SEQ_FILE_PATTERN = re.compile(r"^(\d+)-")

SEVERITY_TO_PRIORITY: dict[str, str] = {
    "critical": "Critical",
    "high": "High",
    "medium": "Medium",
    "low": "Low",
}

PROPOSAL_TYPE_TO_DIR: dict[str, str] = {
    "defect": DEFECT_DIR,
    "enhancement": FEATURE_DIR,
}

_TITLE_NON_ALPHANUM = re.compile(r"[^a-z0-9]+")


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


def _slugify_title(title: str) -> str:
    """Convert a title to a filename-safe kebab-case slug."""
    slug = _TITLE_NON_ALPHANUM.sub("-", title.lower()).strip("-")
    return slug[:TITLE_SLUG_MAX_LEN]


def _next_sequence_number(directory: str) -> int:
    """Return the next available sequence number for a backlog directory.

    Scans for files matching ##-*.md and returns max_found + 1.
    Returns 1 if the directory is empty or does not exist.
    """
    path = Path(directory)
    if not path.exists():
        return 1
    max_num = 0
    for f in path.glob("*.md"):
        match = SEQ_FILE_PATTERN.match(f.name)
        if match:
            max_num = max(max_num, int(match.group(1)))
    return max_num + 1


def _write_backlog_item(proposal: Proposal, target_dir: str, investigation_slug: str) -> str:
    """Write a single proposal as a backlog markdown file.

    Creates the target directory if it does not exist.

    Args:
        proposal: The proposal to file.
        target_dir: Target backlog directory path.
        investigation_slug: Slug of the originating investigation item.

    Returns:
        Absolute path of the written file.
    """
    priority = SEVERITY_TO_PRIORITY.get(proposal.severity, "Medium")
    seq = _next_sequence_number(target_dir)
    slug = _slugify_title(proposal.title)
    filename = f"{seq:02d}-{slug}.md"
    target_path = Path(target_dir)
    target_path.mkdir(parents=True, exist_ok=True)
    filepath = target_path / filename

    content = (
        f"# {proposal.title}\n\n"
        f"## Status: Open\n\n"
        f"## Priority: {priority}\n\n"
        f"## Summary\n\n"
        f"{proposal.description}\n\n"
        f"## Source\n\n"
        f"Filed from investigation `{investigation_slug}`, proposal #{proposal.number}.\n"
    )
    filepath.write_text(content, encoding="utf-8")
    logger.info(
        "Filed proposal number=%d type=%s to %s", proposal.number, proposal.proposal_type, filepath
    )
    return str(filepath)


def file_accepted_proposals(proposal_set: ProposalSet) -> None:
    """File all accepted proposals in proposal_set as standard backlog items.

    Iterates over proposals with status == 'accepted'. For each:
    - Routes to DEFECT_DIR (defects) or FEATURE_DIR (enhancements)
    - Assigns the next available sequence number in that directory
    - Writes a standard backlog markdown file
    - Sets proposal.filed_path to the written file path

    Already-filed proposals (filed_path is set) are skipped for idempotency.
    """
    for proposal in proposal_set.proposals:
        if proposal.status != "accepted":
            continue
        if proposal.filed_path is not None:
            continue  # Already filed; skip for idempotency
        target_dir = PROPOSAL_TYPE_TO_DIR.get(proposal.proposal_type)
        if target_dir is None:
            logger.warning(
                "Unknown proposal_type=%s for proposal number=%d; skipping filing",
                proposal.proposal_type,
                proposal.number,
            )
            continue
        proposal.filed_path = _write_backlog_item(proposal, target_dir, proposal_set.slug)


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
