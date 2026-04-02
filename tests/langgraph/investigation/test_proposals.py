# tests/langgraph/investigation/test_proposals.py
# Unit tests for proposal data model, persistence, and response parsing.
# Design: docs/plans/2026-04-02-82-investigation-workflow-with-slack-proposals-design.md

"""Tests for langgraph_pipeline.investigation.proposals."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from langgraph_pipeline.investigation.proposals import (
    Proposal,
    ProposalSet,
    load_proposals,
    parse_approval_response,
    save_proposals,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────


def _make_proposal(number: int = 1) -> Proposal:
    """Return a minimal Proposal for testing."""
    return Proposal(
        number=number,
        proposal_type="defect",
        title=f"Proposal {number} title",
        description=f"Description for proposal {number}",
        severity="medium",
    )


def _make_proposal_set(proposal_count: int = 2) -> ProposalSet:
    """Return a ProposalSet with proposal_count proposals."""
    return ProposalSet(
        slug="test-slug",
        generated_at="2026-04-02T12:00:00Z",
        proposals=[_make_proposal(i + 1) for i in range(proposal_count)],
    )


# ─── Serialization round-trip ─────────────────────────────────────────────────


class TestProposalRoundTrip:
    """Proposal and ProposalSet survive a save/load cycle unchanged."""

    def test_proposal_fields_preserved(self, tmp_path: Path) -> None:
        proposal_set = ProposalSet(
            slug="round-trip-slug",
            generated_at="2026-04-02T09:00:00Z",
            proposals=[
                Proposal(
                    number=1,
                    proposal_type="enhancement",
                    title="Add caching layer",
                    description="Cache DB results to reduce latency",
                    severity="high",
                    status="accepted",
                    filed_path="docs/feature-backlog/10-add-caching.md",
                ),
                Proposal(
                    number=2,
                    proposal_type="defect",
                    title="Fix null pointer",
                    description="Crashes on empty input",
                    severity="critical",
                ),
            ],
            status="partial",
            slack_channel_id="C12345",
            slack_thread_ts="1712050000.000001",
            reply_text="1",
        )
        save_proposals(proposal_set, tmp_path)
        loaded = load_proposals(tmp_path)
        assert loaded is not None

        assert loaded.slug == "round-trip-slug"
        assert loaded.generated_at == "2026-04-02T09:00:00Z"
        assert loaded.status == "partial"
        assert loaded.slack_channel_id == "C12345"
        assert loaded.slack_thread_ts == "1712050000.000001"
        assert loaded.reply_text == "1"
        assert len(loaded.proposals) == 2

        p1 = loaded.proposals[0]
        assert p1.number == 1
        assert p1.proposal_type == "enhancement"
        assert p1.title == "Add caching layer"
        assert p1.severity == "high"
        assert p1.status == "accepted"
        assert p1.filed_path == "docs/feature-backlog/10-add-caching.md"

        p2 = loaded.proposals[1]
        assert p2.number == 2
        assert p2.proposal_type == "defect"
        assert p2.status == "pending"
        assert p2.filed_path is None

    def test_default_status_values(self, tmp_path: Path) -> None:
        """Proposals and ProposalSets default to 'pending' status."""
        proposal_set = _make_proposal_set(1)
        save_proposals(proposal_set, tmp_path)
        loaded = load_proposals(tmp_path)
        assert loaded is not None
        assert loaded.status == "pending"
        assert loaded.proposals[0].status == "pending"

    def test_optional_fields_none_by_default(self, tmp_path: Path) -> None:
        proposal_set = _make_proposal_set(1)
        save_proposals(proposal_set, tmp_path)
        loaded = load_proposals(tmp_path)
        assert loaded is not None
        assert loaded.slack_channel_id is None
        assert loaded.slack_thread_ts is None
        assert loaded.reply_text is None
        assert loaded.proposals[0].filed_path is None


# ─── save_proposals / load_proposals ─────────────────────────────────────────


class TestPersistence:
    """save_proposals and load_proposals write and read proposals.yaml correctly."""

    def test_creates_workspace_dir(self, tmp_path: Path) -> None:
        nested = tmp_path / "a" / "b" / "workspace"
        proposal_set = _make_proposal_set(1)
        save_proposals(proposal_set, nested)
        assert (nested / "proposals.yaml").exists()

    def test_load_returns_none_for_missing_file(self, tmp_path: Path) -> None:
        result = load_proposals(tmp_path)
        assert result is None

    def test_load_returns_none_for_empty_dir(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty-workspace"
        empty.mkdir()
        assert load_proposals(empty) is None

    def test_proposals_yaml_is_valid_yaml(self, tmp_path: Path) -> None:
        import yaml

        proposal_set = _make_proposal_set(3)
        save_proposals(proposal_set, tmp_path)
        with open(tmp_path / "proposals.yaml") as fh:
            data = yaml.safe_load(fh)
        assert isinstance(data, dict)
        assert data["slug"] == "test-slug"
        assert len(data["proposals"]) == 3

    def test_overwrite_preserves_latest(self, tmp_path: Path) -> None:
        """Saving twice overwrites with the second version."""
        first = _make_proposal_set(1)
        save_proposals(first, tmp_path)
        second = _make_proposal_set(3)
        second.slug = "updated-slug"
        save_proposals(second, tmp_path)
        loaded = load_proposals(tmp_path)
        assert loaded is not None
        assert loaded.slug == "updated-slug"
        assert len(loaded.proposals) == 3


# ─── parse_approval_response ──────────────────────────────────────────────────


class TestParseApprovalResponse:
    """parse_approval_response correctly maps text replies to accepted numbers."""

    # Strategy 1: "all" / "yes"

    def test_all_returns_full_set(self) -> None:
        assert parse_approval_response("all", 4) == {1, 2, 3, 4}

    def test_yes_returns_full_set(self) -> None:
        assert parse_approval_response("yes", 3) == {1, 2, 3}

    def test_all_case_insensitive(self) -> None:
        assert parse_approval_response("ALL", 2) == {1, 2}

    def test_all_with_whitespace(self) -> None:
        assert parse_approval_response("  all  ", 2) == {1, 2}

    # Strategy 2: "none" / "no"

    def test_none_returns_empty_set(self) -> None:
        assert parse_approval_response("none", 4) == set()

    def test_no_returns_empty_set(self) -> None:
        assert parse_approval_response("no", 3) == set()

    def test_none_case_insensitive(self) -> None:
        assert parse_approval_response("NONE", 2) == set()

    # Strategy 3: comma/space-separated numbers

    def test_comma_separated_numbers(self) -> None:
        assert parse_approval_response("1, 3, 5", 5) == {1, 3, 5}

    def test_space_separated_numbers(self) -> None:
        assert parse_approval_response("1 3 5", 5) == {1, 3, 5}

    def test_mixed_comma_and_spaces(self) -> None:
        assert parse_approval_response("2,  4", 5) == {2, 4}

    def test_single_number(self) -> None:
        assert parse_approval_response("2", 3) == {2}

    def test_out_of_range_numbers_ignored(self) -> None:
        """Numbers outside 1..proposal_count are silently dropped."""
        assert parse_approval_response("0, 1, 3, 99", 3) == {1, 3}

    def test_all_out_of_range_returns_empty(self) -> None:
        assert parse_approval_response("10, 20", 5) == set()

    # Strategy 4: "all except ..." pattern

    def test_all_except_single_number(self) -> None:
        assert parse_approval_response("ALL EXCEPT 2", 4) == {1, 3, 4}

    def test_all_except_multiple_numbers(self) -> None:
        assert parse_approval_response("all except 1, 4", 4) == {2, 3}

    def test_all_except_case_insensitive(self) -> None:
        assert parse_approval_response("All Except 3", 3) == {1, 2}

    def test_all_except_out_of_range_ignored(self) -> None:
        """Numbers out of range in 'all except' are silently ignored."""
        assert parse_approval_response("all except 99", 3) == {1, 2, 3}

    # Whitespace variations

    def test_leading_trailing_whitespace(self) -> None:
        assert parse_approval_response("  yes  ", 2) == {1, 2}

    def test_extra_internal_whitespace_in_numbers(self) -> None:
        assert parse_approval_response("1   2   3", 5) == {1, 2, 3}


# ─── LLM fallback ────────────────────────────────────────────────────────────


class TestParseApprovalResponseLlmFallback:
    """Ambiguous text falls back to Claude Haiku."""

    @patch("langgraph_pipeline.investigation.proposals.call_claude")
    def test_llm_fallback_invoked_for_free_text(self, mock_call: MagicMock) -> None:
        mock_result = MagicMock()
        mock_result.failure_reason = None
        mock_result.text = "[2, 3]"
        mock_call.return_value = mock_result

        result = parse_approval_response("yes please approve the second and third", 4)
        assert result == {2, 3}
        mock_call.assert_called_once()

    @patch("langgraph_pipeline.investigation.proposals.call_claude")
    def test_llm_fallback_filters_out_of_range(self, mock_call: MagicMock) -> None:
        mock_result = MagicMock()
        mock_result.failure_reason = None
        mock_result.text = "[1, 5, 99]"
        mock_call.return_value = mock_result

        result = parse_approval_response("approve one and the last two", 3)
        assert result == {1}

    @patch("langgraph_pipeline.investigation.proposals.call_claude")
    def test_llm_fallback_failure_returns_empty_set(self, mock_call: MagicMock) -> None:
        mock_result = MagicMock()
        mock_result.failure_reason = "quota_exhausted"
        mock_result.text = ""
        mock_call.return_value = mock_result

        result = parse_approval_response("looks good to me", 3)
        assert result == set()

    @patch("langgraph_pipeline.investigation.proposals.call_claude")
    def test_llm_fallback_malformed_json_returns_empty_set(self, mock_call: MagicMock) -> None:
        mock_result = MagicMock()
        mock_result.failure_reason = None
        mock_result.text = "Sorry, I cannot parse that."
        mock_call.return_value = mock_result

        result = parse_approval_response("something completely ambiguous", 3)
        assert result == set()
