# tests/langgraph/web/test_execution_tree.py
# Unit tests for the execution_tree helper module.
# Design: docs/plans/2026-03-28-71-execution-history-redesign-design.md (D1, D2, D3)

"""Tests for langgraph_pipeline.web.helpers.execution_tree.

Covers:
- build_tree(): recursive nesting, no depth limit (D1)
- resolve_display_name(): three-tier fallback chain (D2)
- classify_node_type(): node type classification
- Deduplication by run_id (D3)
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from langgraph_pipeline.web.helpers.execution_tree import (
    TreeNode,
    build_tree,
    classify_node_type,
    resolve_display_name,
    _deduplicate_rows,
    _extract_status,
    _is_more_complete,
)

# ─── Constants ────────────────────────────────────────────────────────────────

FIXTURE_ROOT_ID = "root-0000-aaaa-1111"
FIXTURE_CHILD_A_ID = "child-aaaa-2222-3333"
FIXTURE_CHILD_B_ID = "child-bbbb-4444-5555"
FIXTURE_GRANDCHILD_ID = "grand-cccc-6666-7777"
FIXTURE_GREAT_GRANDCHILD_ID = "great-dddd-8888-9999"
FIXTURE_SLUG = "my-feature-abc12345"
FIXTURE_TIMESTAMP_START = "2026-03-28T10:00:00"
FIXTURE_TIMESTAMP_END = "2026-03-28T10:05:00"
FIXTURE_CREATED_AT = "2026-03-28T10:00:01"


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_row(
    run_id: str = FIXTURE_CHILD_A_ID,
    parent_run_id: str | None = FIXTURE_ROOT_ID,
    name: str = "intake",
    start_time: str = FIXTURE_TIMESTAMP_START,
    end_time: str | None = FIXTURE_TIMESTAMP_END,
    error: str | None = None,
    metadata: dict | None = None,
    model: str = "",
    created_at: str = FIXTURE_CREATED_AT,
) -> dict:
    """Create a minimal trace row dict matching the DB schema."""
    return {
        "run_id": run_id,
        "parent_run_id": parent_run_id,
        "name": name,
        "start_time": start_time,
        "end_time": end_time,
        "error": error,
        "metadata_json": json.dumps(metadata or {}),
        "inputs_json": json.dumps({}),
        "outputs_json": json.dumps({}),
        "model": model,
        "created_at": created_at,
    }


# ─── build_tree tests (D1: recursive nesting) ────────────────────────────────


class TestBuildTree:
    """Tests for build_tree() recursive tree assembly."""

    def test_empty_rows_returns_empty_list(self) -> None:
        result = build_tree(FIXTURE_ROOT_ID, [])
        assert result == []

    def test_single_child(self) -> None:
        rows = [_make_row(run_id=FIXTURE_CHILD_A_ID, parent_run_id=FIXTURE_ROOT_ID, name="intake")]
        result = build_tree(FIXTURE_ROOT_ID, rows)
        assert len(result) == 1
        assert result[0].run_id == FIXTURE_CHILD_A_ID
        assert result[0].display_name == "intake"
        assert result[0].children == []

    def test_two_level_nesting(self) -> None:
        """Child with one grandchild."""
        rows = [
            _make_row(run_id=FIXTURE_CHILD_A_ID, parent_run_id=FIXTURE_ROOT_ID, name="execute_plan"),
            _make_row(run_id=FIXTURE_GRANDCHILD_ID, parent_run_id=FIXTURE_CHILD_A_ID, name="task_runner"),
        ]
        result = build_tree(FIXTURE_ROOT_ID, rows)
        assert len(result) == 1
        parent = result[0]
        assert parent.run_id == FIXTURE_CHILD_A_ID
        assert len(parent.children) == 1
        assert parent.children[0].run_id == FIXTURE_GRANDCHILD_ID

    def test_three_level_nesting_no_depth_limit(self) -> None:
        """Root -> child -> grandchild -> great-grandchild (verifies no depth limit)."""
        rows = [
            _make_row(run_id=FIXTURE_CHILD_A_ID, parent_run_id=FIXTURE_ROOT_ID, name="execute_plan"),
            _make_row(run_id=FIXTURE_GRANDCHILD_ID, parent_run_id=FIXTURE_CHILD_A_ID, name="claude-agent"),
            _make_row(
                run_id=FIXTURE_GREAT_GRANDCHILD_ID,
                parent_run_id=FIXTURE_GRANDCHILD_ID,
                name="Read",
            ),
        ]
        result = build_tree(FIXTURE_ROOT_ID, rows)
        assert len(result) == 1
        level1 = result[0]
        assert len(level1.children) == 1
        level2 = level1.children[0]
        assert len(level2.children) == 1
        level3 = level2.children[0]
        assert level3.run_id == FIXTURE_GREAT_GRANDCHILD_ID
        assert level3.name == "Read"
        assert level3.children == []

    def test_multiple_children_at_same_level(self) -> None:
        """Root has two direct children, each a leaf."""
        rows = [
            _make_row(run_id=FIXTURE_CHILD_A_ID, parent_run_id=FIXTURE_ROOT_ID, name="intake"),
            _make_row(run_id=FIXTURE_CHILD_B_ID, parent_run_id=FIXTURE_ROOT_ID, name="plan_creation"),
        ]
        result = build_tree(FIXTURE_ROOT_ID, rows)
        assert len(result) == 2
        names = {n.display_name for n in result}
        assert "intake" in names
        assert "plan_creation" in names

    def test_rows_with_missing_run_id_skipped(self) -> None:
        """Rows without run_id are silently skipped."""
        rows = [
            _make_row(run_id=FIXTURE_CHILD_A_ID, parent_run_id=FIXTURE_ROOT_ID, name="intake"),
            {"run_id": "", "parent_run_id": FIXTURE_ROOT_ID, "name": "bad"},
        ]
        result = build_tree(FIXTURE_ROOT_ID, rows)
        assert len(result) == 1

    def test_node_type_and_status_populated(self) -> None:
        """TreeNode fields are correctly populated from the row."""
        rows = [
            _make_row(
                run_id=FIXTURE_CHILD_A_ID,
                parent_run_id=FIXTURE_ROOT_ID,
                name="Read",
                end_time=FIXTURE_TIMESTAMP_END,
            ),
        ]
        result = build_tree(FIXTURE_ROOT_ID, rows)
        node = result[0]
        assert node.node_type == "tool_call"
        assert node.status == "success"


# ─── resolve_display_name tests (D2: three-tier fallback) ────────────────────


class TestResolveDisplayName:
    """Tests for three-tier name resolution."""

    def test_tier0_uses_own_name_when_not_langgraph(self) -> None:
        """Normal names are returned as-is."""
        row = _make_row(name="execute_plan")
        assert resolve_display_name(row) == "execute_plan"

    def test_tier1_metadata_slug_when_name_is_langgraph(self) -> None:
        """When name is 'LangGraph', fall back to metadata slug."""
        row = _make_row(
            name="LangGraph",
            metadata={"item_slug": FIXTURE_SLUG},
        )
        assert resolve_display_name(row) == FIXTURE_SLUG

    def test_tier1_metadata_slug_field(self) -> None:
        """The 'slug' field in metadata also works."""
        row = _make_row(
            name="LangGraph",
            metadata={"slug": "alt-slug-xyz"},
        )
        assert resolve_display_name(row) == "alt-slug-xyz"

    def test_tier1_item_slug_preferred_over_slug(self) -> None:
        """item_slug takes precedence over slug."""
        row = _make_row(
            name="LangGraph",
            metadata={"item_slug": "preferred-slug", "slug": "fallback-slug"},
        )
        assert resolve_display_name(row) == "preferred-slug"

    def test_tier2_child_span_scan(self) -> None:
        """When name is LangGraph and metadata has no slug, scan children."""
        row = _make_row(name="LangGraph", metadata={})
        children = [
            _make_row(name="intake", metadata={"item_slug": "child-found-slug"}),
        ]
        assert resolve_display_name(row, children) == "child-found-slug"

    def test_tier2_skips_langgraph_in_children(self) -> None:
        """Children with slug='LangGraph' are skipped."""
        row = _make_row(name="LangGraph", metadata={})
        children = [
            _make_row(name="child1", metadata={"slug": "LangGraph"}),
            _make_row(name="child2", metadata={"item_slug": "real-slug"}),
        ]
        assert resolve_display_name(row, children) == "real-slug"

    def test_tier3_run_id_prefix(self) -> None:
        """When all tiers fail, use first 8 chars of run_id."""
        row = _make_row(
            run_id="abcdef01-2345-6789-abcd-ef0123456789",
            name="LangGraph",
            metadata={},
        )
        assert resolve_display_name(row, []) == "abcdef01"

    def test_tier3_with_no_children(self) -> None:
        """No children provided, falls through to run_id prefix."""
        row = _make_row(
            run_id="12345678-aaaa-bbbb-cccc-ddddeeee",
            name="LangGraph",
            metadata={},
        )
        assert resolve_display_name(row, None) == "12345678"

    def test_empty_name_treated_like_langgraph(self) -> None:
        """Empty name triggers the same fallback chain."""
        row = _make_row(
            run_id="fedcba98-7654-3210",
            name="",
            metadata={"slug": "found-by-meta"},
        )
        assert resolve_display_name(row) == "found-by-meta"

    def test_langgraph_never_returned(self) -> None:
        """Even if metadata slug is 'LangGraph', it's not returned."""
        row = _make_row(
            run_id="aabbccdd-0000-1111",
            name="LangGraph",
            metadata={"slug": "LangGraph"},
        )
        # No children, so falls to run_id prefix
        result = resolve_display_name(row, [])
        assert result != "LangGraph"
        assert result == "aabbccdd"


# ─── classify_node_type tests ────────────────────────────────────────────────


class TestClassifyNodeType:
    """Tests for node type classification."""

    def test_tool_call_names(self) -> None:
        for tool in ("Read", "Edit", "Write", "Bash", "Grep", "Glob", "Skill", "TodoWrite"):
            row = _make_row(name=tool)
            assert classify_node_type(tool, row) == "tool_call", f"Expected tool_call for {tool}"

    def test_agent_name(self) -> None:
        row = _make_row(name="agent-session")
        assert classify_node_type("agent-session", row) == "agent"

    def test_subgraph_name(self) -> None:
        row = _make_row(name="executor-subgraph")
        assert classify_node_type("executor-subgraph", row) == "subgraph"

    def test_explicit_metadata_type_tool(self) -> None:
        row = _make_row(name="custom-op", metadata={"run_type": "tool"})
        assert classify_node_type("custom-op", row) == "tool_call"

    def test_explicit_metadata_type_llm(self) -> None:
        row = _make_row(name="custom-op", metadata={"run_type": "llm"})
        assert classify_node_type("custom-op", row) == "agent"

    def test_model_field_implies_agent(self) -> None:
        row = _make_row(name="custom-chain", model="claude-sonnet-4-6")
        assert classify_node_type("custom-chain", row) == "agent"

    def test_default_graph_node(self) -> None:
        row = _make_row(name="intake_node")
        assert classify_node_type("intake_node", row) == "graph_node"

    def test_case_insensitive(self) -> None:
        row = _make_row(name="BASH")
        assert classify_node_type("BASH", row) == "tool_call"


# ─── Deduplication tests (D3) ────────────────────────────────────────────────


class TestDeduplication:
    """Tests for UI-level deduplication by run_id."""

    def test_no_duplicates_pass_through(self) -> None:
        rows = [
            _make_row(run_id="aaa"),
            _make_row(run_id="bbb"),
        ]
        result = _deduplicate_rows(rows)
        assert len(result) == 2

    def test_duplicate_keeps_row_with_end_time(self) -> None:
        """When one row has end_time and the other doesn't, keep the complete one."""
        rows = [
            _make_row(run_id="dup-111", end_time=None, created_at="2026-03-28T10:00:00"),
            _make_row(run_id="dup-111", end_time=FIXTURE_TIMESTAMP_END, created_at="2026-03-28T10:00:01"),
        ]
        result = _deduplicate_rows(rows)
        assert len(result) == 1
        assert result[0]["end_time"] == FIXTURE_TIMESTAMP_END

    def test_duplicate_keeps_later_created_at_when_both_have_end(self) -> None:
        """Both have end_time: keep the one with later created_at."""
        rows = [
            _make_row(run_id="dup-222", end_time="2026-03-28T10:04:00", created_at="2026-03-28T10:00:00"),
            _make_row(run_id="dup-222", end_time="2026-03-28T10:05:00", created_at="2026-03-28T10:05:01"),
        ]
        result = _deduplicate_rows(rows)
        assert len(result) == 1
        assert result[0]["created_at"] == "2026-03-28T10:05:01"

    def test_order_preserved(self) -> None:
        """First-seen order is preserved after dedup."""
        rows = [
            _make_row(run_id="first"),
            _make_row(run_id="second"),
            _make_row(run_id="first", end_time=FIXTURE_TIMESTAMP_END),
        ]
        result = _deduplicate_rows(rows)
        assert len(result) == 2
        assert result[0]["run_id"] == "first"
        assert result[1]["run_id"] == "second"

    def test_rows_without_run_id_skipped(self) -> None:
        rows = [
            _make_row(run_id="valid"),
            {"run_id": "", "name": "bad"},
        ]
        result = _deduplicate_rows(rows)
        assert len(result) == 1
        assert result[0]["run_id"] == "valid"

    def test_triple_duplicate_keeps_best(self) -> None:
        """Three rows with same run_id: the one with end_time and latest created_at wins."""
        rows = [
            _make_row(run_id="trip-333", end_time=None, created_at="2026-03-28T10:00:00"),
            _make_row(run_id="trip-333", end_time=FIXTURE_TIMESTAMP_END, created_at="2026-03-28T10:00:01"),
            _make_row(run_id="trip-333", end_time=FIXTURE_TIMESTAMP_END, created_at="2026-03-28T10:00:02"),
        ]
        result = _deduplicate_rows(rows)
        assert len(result) == 1
        assert result[0]["created_at"] == "2026-03-28T10:00:02"


# ─── _is_more_complete tests ─────────────────────────────────────────────────


class TestIsMoreComplete:
    def test_end_time_wins_over_no_end_time(self) -> None:
        candidate = _make_row(end_time=FIXTURE_TIMESTAMP_END)
        existing = _make_row(end_time=None)
        assert _is_more_complete(candidate, existing) is True

    def test_no_end_time_loses_to_end_time(self) -> None:
        candidate = _make_row(end_time=None)
        existing = _make_row(end_time=FIXTURE_TIMESTAMP_END)
        assert _is_more_complete(candidate, existing) is False

    def test_later_created_at_wins_when_both_have_end(self) -> None:
        candidate = _make_row(end_time=FIXTURE_TIMESTAMP_END, created_at="2026-03-28T10:05:00")
        existing = _make_row(end_time=FIXTURE_TIMESTAMP_END, created_at="2026-03-28T10:00:00")
        assert _is_more_complete(candidate, existing) is True

    def test_earlier_created_at_loses_when_both_have_end(self) -> None:
        candidate = _make_row(end_time=FIXTURE_TIMESTAMP_END, created_at="2026-03-28T10:00:00")
        existing = _make_row(end_time=FIXTURE_TIMESTAMP_END, created_at="2026-03-28T10:05:00")
        assert _is_more_complete(candidate, existing) is False


# ─── _extract_status tests ───────────────────────────────────────────────────


class TestExtractStatus:
    def test_error(self) -> None:
        assert _extract_status({"error": "boom"}) == "error"

    def test_success(self) -> None:
        assert _extract_status({"end_time": "2026-03-28T10:05:00"}) == "success"

    def test_running(self) -> None:
        assert _extract_status({"start_time": "2026-03-28T10:00:00"}) == "running"

    def test_unknown(self) -> None:
        assert _extract_status({}) == "unknown"


# ─── Integration: build_tree with dedup and name resolution ──────────────────


class TestBuildTreeIntegration:
    """Integration tests combining D1 + D2 + D3."""

    def test_dedup_during_tree_build(self) -> None:
        """Duplicate rows for same run_id are merged before tree assembly."""
        rows = [
            _make_row(
                run_id=FIXTURE_CHILD_A_ID,
                parent_run_id=FIXTURE_ROOT_ID,
                name="intake",
                end_time=None,
                created_at="2026-03-28T10:00:00",
            ),
            _make_row(
                run_id=FIXTURE_CHILD_A_ID,
                parent_run_id=FIXTURE_ROOT_ID,
                name="intake",
                end_time=FIXTURE_TIMESTAMP_END,
                created_at="2026-03-28T10:00:01",
            ),
        ]
        result = build_tree(FIXTURE_ROOT_ID, rows)
        assert len(result) == 1
        assert result[0].end_time == FIXTURE_TIMESTAMP_END

    def test_langgraph_name_resolved_via_children(self) -> None:
        """Root's child named 'LangGraph' gets name from grandchild metadata."""
        rows = [
            _make_row(
                run_id=FIXTURE_CHILD_A_ID,
                parent_run_id=FIXTURE_ROOT_ID,
                name="LangGraph",
                metadata={},
            ),
            _make_row(
                run_id=FIXTURE_GRANDCHILD_ID,
                parent_run_id=FIXTURE_CHILD_A_ID,
                name="intake",
                metadata={"item_slug": "resolved-from-grandchild"},
            ),
        ]
        result = build_tree(FIXTURE_ROOT_ID, rows)
        assert len(result) == 1
        node = result[0]
        assert node.display_name == "resolved-from-grandchild"
        assert node.name == "LangGraph"  # original name preserved

    def test_deep_tree_with_tool_calls(self) -> None:
        """Full pipeline tree: root -> phase -> executor -> agent -> tool -> sub-tool."""
        rows = [
            _make_row(run_id="phase-1", parent_run_id=FIXTURE_ROOT_ID, name="execute_plan"),
            _make_row(run_id="executor-1", parent_run_id="phase-1", name="task_runner_subgraph"),
            _make_row(run_id="agent-1", parent_run_id="executor-1", name="coder-agent", model="claude-sonnet-4-6"),
            _make_row(run_id="tool-1", parent_run_id="agent-1", name="Read"),
            _make_row(run_id="tool-2", parent_run_id="agent-1", name="Edit"),
            _make_row(run_id="skill-1", parent_run_id="agent-1", name="Skill"),
            _make_row(run_id="sub-tool-1", parent_run_id="skill-1", name="Bash"),
        ]
        result = build_tree(FIXTURE_ROOT_ID, rows)

        # Level 1: execute_plan
        assert len(result) == 1
        phase = result[0]
        assert phase.display_name == "execute_plan"
        assert phase.node_type == "graph_node"

        # Level 2: task_runner_subgraph
        assert len(phase.children) == 1
        executor = phase.children[0]
        assert executor.node_type == "subgraph"

        # Level 3: coder-agent (has model => agent type)
        assert len(executor.children) == 1
        agent = executor.children[0]
        assert agent.node_type == "agent"

        # Level 4: Read, Edit, Skill (tool_calls)
        assert len(agent.children) == 3
        tool_types = {c.node_type for c in agent.children}
        assert tool_types == {"tool_call"}

        # Level 5: Bash under Skill (sub-tool-call, no depth limit)
        skill_node = next(c for c in agent.children if c.name == "Skill")
        assert len(skill_node.children) == 1
        sub_tool = skill_node.children[0]
        assert sub_tool.name == "Bash"
        assert sub_tool.node_type == "tool_call"


# ─── TracingProxy.get_full_tree tests ────────────────────────────────────────


class TestGetFullTree:
    """Tests for the get_full_tree method on TracingProxy."""

    def test_empty_tree(self) -> None:
        """Root with no children returns empty list."""
        proxy = MagicMock()
        proxy.get_children_batch.return_value = {}
        # Directly call the real method logic
        from langgraph_pipeline.web.proxy import TracingProxy
        result = TracingProxy.get_full_tree(proxy, "root-id")
        assert result == []

    def test_single_level(self) -> None:
        """Root with direct children only."""
        proxy = MagicMock()
        child_row = _make_row(run_id="child-1", parent_run_id="root-id", name="intake")
        proxy.get_children_batch.side_effect = [
            {"root-id": [child_row]},  # first call: root's children
            {},  # second call: child-1 has no children
        ]
        from langgraph_pipeline.web.proxy import TracingProxy
        result = TracingProxy.get_full_tree(proxy, "root-id")
        assert len(result) == 1
        assert result[0]["run_id"] == "child-1"

    def test_multi_level_bfs(self) -> None:
        """Root -> child -> grandchild traversal."""
        proxy = MagicMock()
        child_row = _make_row(run_id="child-1", parent_run_id="root-id", name="execute")
        grandchild_row = _make_row(run_id="grand-1", parent_run_id="child-1", name="Read")
        proxy.get_children_batch.side_effect = [
            {"root-id": [child_row]},
            {"child-1": [grandchild_row]},
            {},  # grand-1 has no children
        ]
        from langgraph_pipeline.web.proxy import TracingProxy
        result = TracingProxy.get_full_tree(proxy, "root-id")
        assert len(result) == 2
        assert result[0]["run_id"] == "child-1"
        assert result[1]["run_id"] == "grand-1"
