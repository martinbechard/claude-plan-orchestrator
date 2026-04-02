# tests/langgraph/pipeline/nodes/test_investigation.py
# Unit tests for the run_investigation LangGraph node.
# Design: docs/plans/2026-04-02-82-investigation-workflow-with-slack-proposals-design.md

"""Tests for langgraph_pipeline.pipeline.nodes.investigation.run_investigation."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from langgraph_pipeline.pipeline.nodes.investigation import run_investigation


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
