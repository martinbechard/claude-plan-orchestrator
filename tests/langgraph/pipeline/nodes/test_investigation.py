# tests/langgraph/pipeline/nodes/test_investigation.py
# Unit tests for run_investigation and process_investigation LangGraph nodes.
# Design: docs/plans/2026-04-02-82-investigation-workflow-with-slack-proposals-design.md

"""Tests for langgraph_pipeline.pipeline.nodes.investigation."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from langgraph_pipeline.investigation.proposals import Proposal, ProposalSet, save_proposals
from langgraph_pipeline.pipeline.nodes.investigation import (
    process_investigation,
    run_investigation,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_state(**overrides) -> dict:
    """Build a minimal PipelineState dict for investigation items."""
    base = {
        "item_path": "docs/investigation-backlog/82-test-item.md",
        "item_slug": "82-test-item",
        "item_type": "investigation",
        "item_name": "82 Test Item",
        "workspace_path": None,
        "clause_register_path": None,
        "five_whys_path": None,
        "plan_path": None,
        "design_doc_path": None,
        "verification_cycle": 0,
        "verification_history": [],
        "should_stop": False,
        "rate_limited": False,
        "rate_limit_reset": None,
        "quota_exhausted": False,
        "session_cost_usd": 0.0,
        "session_input_tokens": 0,
        "session_output_tokens": 0,
        "intake_count_defects": 0,
        "intake_count_features": 0,
        "budget_cap_usd": None,
        "executor_deadlock": False,
        "executor_deadlock_details": None,
        "langsmith_root_run_id": None,
        "last_validation_verdict": None,
        "verification_notes": None,
    }
    base.update(overrides)
    return base


_SAMPLE_PROPOSALS_JSON = json.dumps([
    {
        "type": "defect",
        "title": "Missing null check in archival node",
        "description": "Evidence: archival.py:42 does not check for None before accessing .slug",
        "severity": "high",
    },
    {
        "type": "enhancement",
        "title": "Add retry logic to suspension poller",
        "description": "Evidence: suspension.py:88 exits on first 429 without retry",
        "severity": "medium",
    },
])

_CLAUDE_JSON_RESPONSE = json.dumps({
    "result": f"After investigation, here are the proposals:\n\n```json\n{_SAMPLE_PROPOSALS_JSON}\n```",
    "total_cost_usd": 0.05,
    "usage": {"input_tokens": 1000, "output_tokens": 500},
})


# ─── Test: idempotency ─────────────────────────────────────────────────────────


def test_run_investigation_skips_when_proposals_already_exist(tmp_path):
    """run_investigation returns {} without calling Claude if proposals.yaml exists."""
    from langgraph_pipeline.investigation.proposals import ProposalSet, save_proposals

    # Create a pre-existing proposals.yaml in the workspace
    workspace_dir = tmp_path / "82-test-item"
    existing_set = ProposalSet(
        slug="82-test-item",
        generated_at="2026-04-02T00:00:00Z",
        proposals=[],
    )
    save_proposals(existing_set, workspace_dir)

    state = _make_state()

    with patch(
        "langgraph_pipeline.pipeline.nodes.investigation._run_subprocess"
    ) as mock_subprocess, patch(
        "langgraph_pipeline.pipeline.nodes.investigation._workspace_dir",
        return_value=workspace_dir,
    ):
        result = run_investigation(state)

    mock_subprocess.assert_not_called()
    assert result == {}


# ─── Test: successful proposal generation ─────────────────────────────────────


def test_run_investigation_calls_claude_and_saves_proposals(tmp_path):
    """run_investigation spawns Claude, parses proposals, saves proposals.yaml."""
    from langgraph_pipeline.investigation.proposals import load_proposals

    workspace_dir = tmp_path / "82-test-item"
    item_path = tmp_path / "82-test-item.md"
    clause_path = tmp_path / "clause-register.md"
    five_whys_path = tmp_path / "five-whys.md"

    item_path.write_text("# Investigation Item\nObserved: trace links empty.\n", encoding="utf-8")
    clause_path.write_text("C1 [C-PROB]: trace links empty\n", encoding="utf-8")
    five_whys_path.write_text("Why 1: archival skips trace\n", encoding="utf-8")

    state = _make_state(
        item_path=str(item_path),
        item_slug="82-test-item",
        clause_register_path=str(clause_path),
        five_whys_path=str(five_whys_path),
    )

    with patch(
        "langgraph_pipeline.pipeline.nodes.investigation._run_subprocess",
        return_value=(0, _CLAUDE_JSON_RESPONSE, ""),
    ), patch(
        "langgraph_pipeline.pipeline.nodes.investigation._workspace_dir",
        return_value=workspace_dir,
    ):
        result = run_investigation(state)

    assert result == {}

    saved = load_proposals(workspace_dir)
    assert saved is not None
    assert saved.slug == "82-test-item"
    assert len(saved.proposals) == 2

    p1 = saved.proposals[0]
    assert p1.number == 1
    assert p1.proposal_type == "defect"
    assert p1.title == "Missing null check in archival node"
    assert p1.severity == "high"
    assert p1.status == "pending"

    p2 = saved.proposals[1]
    assert p2.number == 2
    assert p2.proposal_type == "enhancement"
    assert p2.severity == "medium"


# ─── Test: parse failure handling ─────────────────────────────────────────────


def test_run_investigation_handles_parse_failure_gracefully(tmp_path):
    """run_investigation logs a warning and raises on total parse failure."""
    workspace_dir = tmp_path / "82-test-item"
    item_path = tmp_path / "82-test-item.md"
    item_path.write_text("# Investigation Item\n", encoding="utf-8")

    bad_response = json.dumps({
        "result": "I investigated but could not produce JSON. Here is my narrative.",
        "total_cost_usd": 0.02,
        "usage": {"input_tokens": 100, "output_tokens": 50},
    })

    state = _make_state(item_path=str(item_path))

    with patch(
        "langgraph_pipeline.pipeline.nodes.investigation._run_subprocess",
        return_value=(0, bad_response, ""),
    ), patch(
        "langgraph_pipeline.pipeline.nodes.investigation._workspace_dir",
        return_value=workspace_dir,
    ), pytest.raises(ValueError, match="No JSON array found"):
        run_investigation(state)


# ─── Test: Claude subprocess failure ──────────────────────────────────────────


def test_run_investigation_handles_subprocess_failure(tmp_path):
    """run_investigation raises on non-zero subprocess exit code."""
    workspace_dir = tmp_path / "82-test-item"
    item_path = tmp_path / "82-test-item.md"
    item_path.write_text("# Investigation Item\n", encoding="utf-8")

    state = _make_state(item_path=str(item_path))

    with patch(
        "langgraph_pipeline.pipeline.nodes.investigation._run_subprocess",
        return_value=(1, "", "claude: command not found"),
    ), patch(
        "langgraph_pipeline.pipeline.nodes.investigation._workspace_dir",
        return_value=workspace_dir,
    ), pytest.raises(RuntimeError, match="Investigation Claude subprocess failed"):
        run_investigation(state)


# ─── Helpers for process_investigation tests ──────────────────────────────────


def _make_proposal_set(
    slug: str = "82-test-item",
    slack_thread_ts: str = None,
    slack_channel_id: str = None,
    reply_text: str = None,
) -> ProposalSet:
    """Build a ProposalSet with two sample proposals."""
    return ProposalSet(
        slug=slug,
        generated_at="2026-04-02T00:00:00Z",
        slack_thread_ts=slack_thread_ts,
        slack_channel_id=slack_channel_id,
        reply_text=reply_text,
        proposals=[
            Proposal(
                number=1,
                proposal_type="defect",
                title="Missing null check in archival node",
                description="archival.py:42 dereferences slug without None check.",
                severity="high",
            ),
            Proposal(
                number=2,
                proposal_type="enhancement",
                title="Add retry logic to suspension poller",
                description="suspension.py:88 exits on first 429 without retry.",
                severity="medium",
            ),
        ],
    )


# ─── process_investigation: Phase 1 (post proposals) ─────────────────────────


def test_process_investigation_posts_to_slack_when_no_thread_ts(tmp_path):
    """Phase 1: posts proposals to Slack and sets should_stop=True."""
    ws_dir = tmp_path / "82-test-item"
    proposal_set = _make_proposal_set()
    save_proposals(proposal_set, ws_dir)

    state = _make_state(item_slug="82-test-item")

    mock_notifier = MagicMock()
    mock_notifier.post_proposals.return_value = ("1234567890.000001", "C_INV_CH")

    with patch(
        "langgraph_pipeline.pipeline.nodes.investigation._workspace_dir",
        return_value=ws_dir,
    ), patch(
        "langgraph_pipeline.pipeline.nodes.investigation.SlackNotifier",
        return_value=mock_notifier,
    ):
        result = process_investigation(state)

    assert result == {"should_stop": True}
    mock_notifier.post_proposals.assert_called_once_with("82-test-item", proposal_set.proposals)

    from langgraph_pipeline.investigation.proposals import load_proposals
    saved = load_proposals(ws_dir)
    assert saved is not None
    assert saved.slack_thread_ts == "1234567890.000001"
    assert saved.slack_channel_id == "C_INV_CH"


def test_process_investigation_sets_should_stop_when_no_reply_yet(tmp_path):
    """Phase 2: sets should_stop=True when no human reply in thread."""
    ws_dir = tmp_path / "82-test-item"
    proposal_set = _make_proposal_set(
        slack_thread_ts="1234567890.000001",
        slack_channel_id="C_INV_CH",
    )
    save_proposals(proposal_set, ws_dir)

    state = _make_state(item_slug="82-test-item")

    mock_notifier = MagicMock()
    mock_notifier.check_suspension_reply.return_value = None

    with patch(
        "langgraph_pipeline.pipeline.nodes.investigation._workspace_dir",
        return_value=ws_dir,
    ), patch(
        "langgraph_pipeline.pipeline.nodes.investigation.SlackNotifier",
        return_value=mock_notifier,
    ):
        result = process_investigation(state)

    assert result == {"should_stop": True}
    mock_notifier.check_suspension_reply.assert_called_once_with(
        "C_INV_CH", "1234567890.000001"
    )


def test_process_investigation_parses_reply_and_files_proposals(tmp_path):
    """Phase 3: parses reply, files accepted proposals, returns should_stop=False."""
    ws_dir = tmp_path / "82-test-item"
    proposal_set = _make_proposal_set(
        slack_thread_ts="1234567890.000001",
        slack_channel_id="C_INV_CH",
        reply_text="1",
    )
    save_proposals(proposal_set, ws_dir)

    state = _make_state(item_slug="82-test-item")

    mock_notifier = MagicMock()

    defect_dir = tmp_path / "defect-backlog"
    feature_dir = tmp_path / "feature-backlog"
    defect_dir.mkdir()
    feature_dir.mkdir()

    with patch(
        "langgraph_pipeline.pipeline.nodes.investigation._workspace_dir",
        return_value=ws_dir,
    ), patch(
        "langgraph_pipeline.pipeline.nodes.investigation.SlackNotifier",
        return_value=mock_notifier,
    ), patch(
        "langgraph_pipeline.investigation.proposals.DEFECT_DIR",
        str(defect_dir),
    ), patch(
        "langgraph_pipeline.investigation.proposals.PROPOSAL_TYPE_TO_DIR",
        {"defect": str(defect_dir), "enhancement": str(feature_dir)},
    ):
        result = process_investigation(state)

    assert result == {"should_stop": False}

    from langgraph_pipeline.investigation.proposals import load_proposals
    saved = load_proposals(ws_dir)
    assert saved is not None
    assert saved.proposals[0].status == "accepted"
    assert saved.proposals[1].status == "rejected"
    assert saved.status == "partial"
    assert saved.proposals[0].filed_path is not None
    assert saved.proposals[1].filed_path is None

    filed_files = list(defect_dir.glob("*.md"))
    assert len(filed_files) == 1


# ─── file_accepted_proposals tests ────────────────────────────────────────────


def test_file_accepted_proposals_writes_correct_markdown_format(tmp_path):
    """Accepted proposals are written with title, status, priority, summary, source."""
    from langgraph_pipeline.investigation.proposals import file_accepted_proposals

    defect_dir = tmp_path / "defect-backlog"
    defect_dir.mkdir()

    proposal_set = _make_proposal_set()
    proposal_set.proposals[0].status = "accepted"

    with patch(
        "langgraph_pipeline.investigation.proposals.PROPOSAL_TYPE_TO_DIR",
        {"defect": str(defect_dir), "enhancement": str(tmp_path / "feature-backlog")},
    ):
        file_accepted_proposals(proposal_set)

    filed = list(defect_dir.glob("*.md"))
    assert len(filed) == 1

    content = filed[0].read_text(encoding="utf-8")
    assert "# Missing null check in archival node" in content
    assert "## Status: Open" in content
    assert "## Priority: High" in content
    assert "## Summary" in content
    assert "archival.py:42" in content
    assert "## Source" in content
    assert "82-test-item" in content
    assert "proposal #1" in content


def test_file_accepted_proposals_routes_defects_to_defect_backlog(tmp_path):
    """Defect proposals are routed to the defect-backlog directory."""
    from langgraph_pipeline.investigation.proposals import file_accepted_proposals

    defect_dir = tmp_path / "defect-backlog"
    feature_dir = tmp_path / "feature-backlog"
    defect_dir.mkdir()
    feature_dir.mkdir()

    proposal_set = _make_proposal_set()
    proposal_set.proposals[0].status = "accepted"  # defect

    with patch(
        "langgraph_pipeline.investigation.proposals.PROPOSAL_TYPE_TO_DIR",
        {"defect": str(defect_dir), "enhancement": str(feature_dir)},
    ):
        file_accepted_proposals(proposal_set)

    assert len(list(defect_dir.glob("*.md"))) == 1
    assert len(list(feature_dir.glob("*.md"))) == 0


def test_file_accepted_proposals_routes_enhancements_to_feature_backlog(tmp_path):
    """Enhancement proposals are routed to the feature-backlog directory."""
    from langgraph_pipeline.investigation.proposals import file_accepted_proposals

    defect_dir = tmp_path / "defect-backlog"
    feature_dir = tmp_path / "feature-backlog"
    defect_dir.mkdir()
    feature_dir.mkdir()

    proposal_set = _make_proposal_set()
    proposal_set.proposals[1].status = "accepted"  # enhancement

    with patch(
        "langgraph_pipeline.investigation.proposals.PROPOSAL_TYPE_TO_DIR",
        {"defect": str(defect_dir), "enhancement": str(feature_dir)},
    ):
        file_accepted_proposals(proposal_set)

    assert len(list(defect_dir.glob("*.md"))) == 0
    assert len(list(feature_dir.glob("*.md"))) == 1


def test_file_accepted_proposals_sets_filed_path(tmp_path):
    """file_accepted_proposals sets proposal.filed_path to the written file path."""
    from langgraph_pipeline.investigation.proposals import file_accepted_proposals

    defect_dir = tmp_path / "defect-backlog"
    defect_dir.mkdir()

    proposal_set = _make_proposal_set()
    proposal_set.proposals[0].status = "accepted"

    with patch(
        "langgraph_pipeline.investigation.proposals.PROPOSAL_TYPE_TO_DIR",
        {"defect": str(defect_dir), "enhancement": str(tmp_path / "feature-backlog")},
    ):
        file_accepted_proposals(proposal_set)

    assert proposal_set.proposals[0].filed_path is not None
    assert Path(proposal_set.proposals[0].filed_path).exists()
    assert proposal_set.proposals[1].filed_path is None  # rejected, not filed


# ─── Outcome recording tests ──────────────────────────────────────────────────


def test_outcome_recording_accepted_rejected_statuses_persisted(tmp_path):
    """After Phase 3, proposals.yaml records accepted/rejected statuses."""
    ws_dir = tmp_path / "82-test-item"
    proposal_set = _make_proposal_set(
        slack_thread_ts="1234567890.000001",
        slack_channel_id="C_INV_CH",
        reply_text="all",
    )
    save_proposals(proposal_set, ws_dir)

    state = _make_state(item_slug="82-test-item")

    mock_notifier = MagicMock()
    defect_dir = tmp_path / "defect-backlog"
    feature_dir = tmp_path / "feature-backlog"
    defect_dir.mkdir()
    feature_dir.mkdir()

    with patch(
        "langgraph_pipeline.pipeline.nodes.investigation._workspace_dir",
        return_value=ws_dir,
    ), patch(
        "langgraph_pipeline.pipeline.nodes.investigation.SlackNotifier",
        return_value=mock_notifier,
    ), patch(
        "langgraph_pipeline.investigation.proposals.PROPOSAL_TYPE_TO_DIR",
        {"defect": str(defect_dir), "enhancement": str(feature_dir)},
    ):
        process_investigation(state)

    from langgraph_pipeline.investigation.proposals import load_proposals
    saved = load_proposals(ws_dir)
    assert saved is not None
    assert all(p.status == "accepted" for p in saved.proposals)
    assert saved.status == "approved"


def test_rejected_proposals_recorded_with_rejected_status(tmp_path):
    """Proposals not approved are persisted with status='rejected'."""
    ws_dir = tmp_path / "82-test-item"
    proposal_set = _make_proposal_set(
        slack_thread_ts="1234567890.000001",
        slack_channel_id="C_INV_CH",
        reply_text="none",
    )
    save_proposals(proposal_set, ws_dir)

    state = _make_state(item_slug="82-test-item")

    mock_notifier = MagicMock()

    with patch(
        "langgraph_pipeline.pipeline.nodes.investigation._workspace_dir",
        return_value=ws_dir,
    ), patch(
        "langgraph_pipeline.pipeline.nodes.investigation.SlackNotifier",
        return_value=mock_notifier,
    ), patch(
        "langgraph_pipeline.investigation.proposals.PROPOSAL_TYPE_TO_DIR",
        {"defect": str(tmp_path / "defect"), "enhancement": str(tmp_path / "feature")},
    ):
        result = process_investigation(state)

    assert result == {"should_stop": False}

    from langgraph_pipeline.investigation.proposals import load_proposals
    saved = load_proposals(ws_dir)
    assert saved is not None
    assert all(p.status == "rejected" for p in saved.proposals)
    assert saved.status == "rejected"


def test_full_traceability_proposals_yaml_links_slug_statuses_filed_paths(tmp_path):
    """proposals.yaml links investigation slug, proposal IDs, statuses, and filed_paths."""
    ws_dir = tmp_path / "82-test-item"
    proposal_set = _make_proposal_set(
        slack_thread_ts="1234567890.000001",
        slack_channel_id="C_INV_CH",
        reply_text="2",
    )
    save_proposals(proposal_set, ws_dir)

    state = _make_state(item_slug="82-test-item")

    mock_notifier = MagicMock()
    defect_dir = tmp_path / "defect-backlog"
    feature_dir = tmp_path / "feature-backlog"
    feature_dir.mkdir(parents=True)

    with patch(
        "langgraph_pipeline.pipeline.nodes.investigation._workspace_dir",
        return_value=ws_dir,
    ), patch(
        "langgraph_pipeline.pipeline.nodes.investigation.SlackNotifier",
        return_value=mock_notifier,
    ), patch(
        "langgraph_pipeline.investigation.proposals.PROPOSAL_TYPE_TO_DIR",
        {"defect": str(defect_dir), "enhancement": str(feature_dir)},
    ):
        process_investigation(state)

    from langgraph_pipeline.investigation.proposals import load_proposals
    saved = load_proposals(ws_dir)
    assert saved is not None
    assert saved.slug == "82-test-item"

    p1 = saved.proposals[0]
    p2 = saved.proposals[1]

    # Proposal 1 (defect) rejected — no filed_path
    assert p1.status == "rejected"
    assert p1.filed_path is None

    # Proposal 2 (enhancement) accepted — filed_path points to feature-backlog
    assert p2.status == "accepted"
    assert p2.filed_path is not None
    assert "feature-backlog" in p2.filed_path
    assert Path(p2.filed_path).exists()

    # Thread context preserved for full traceability
    assert saved.slack_thread_ts == "1234567890.000001"
    assert saved.slack_channel_id == "C_INV_CH"
    assert saved.reply_text == "2"
