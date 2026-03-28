# tests/langgraph/web/test_execution_tree.py
# Unit tests for the execution_tree helper module.
# Design: docs/plans/2026-03-28-71-execution-history-redesign-design.md (D1, D2, D3, D4, D5)

"""Tests for langgraph_pipeline.web.helpers.execution_tree.

Covers:
- build_tree(): recursive nesting, no depth limit (D1)
- resolve_display_name(): three-tier fallback chain (D2)
- classify_node_type(): node type classification
- Deduplication by run_id (D3)
- Cost aggregation from metadata (D4)
- Wall-clock duration with near-zero replacement (D5)
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from langgraph_pipeline.web.helpers.execution_tree import (
    COST_METADATA_KEY,
    NEAR_ZERO_DURATION_THRESHOLD_SECONDS,
    TreeNode,
    build_tree,
    classify_node_type,
    extract_node_cost,
    resolve_display_name,
    _collect_time_bounds,
    _compute_own_duration,
    _deduplicate_rows,
    _enrich_costs,
    _enrich_durations,
    _extract_status,
    _is_more_complete,
    _parse_timestamp,
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


# ─── D4: Cost Aggregation tests ─────────────────────────────────────────────


# Fixtures for cost tests using realistic-looking values (not round numbers)
FIXTURE_COST_A = 0.3742
FIXTURE_COST_B = 1.0891
FIXTURE_COST_C = 0.0523


class TestExtractNodeCost:
    """Tests for extract_node_cost() — extracting cost from metadata_json."""

    def test_valid_cost(self) -> None:
        meta = json.dumps({COST_METADATA_KEY: FIXTURE_COST_A})
        assert extract_node_cost(meta) == pytest.approx(FIXTURE_COST_A)

    def test_no_cost_key(self) -> None:
        meta = json.dumps({"other_field": "value"})
        assert extract_node_cost(meta) == 0.0

    def test_none_metadata(self) -> None:
        assert extract_node_cost(None) == 0.0

    def test_empty_string_metadata(self) -> None:
        assert extract_node_cost("") == 0.0

    def test_invalid_json(self) -> None:
        assert extract_node_cost("not-json") == 0.0

    def test_zero_cost(self) -> None:
        meta = json.dumps({COST_METADATA_KEY: 0.0})
        assert extract_node_cost(meta) == 0.0

    def test_negative_cost_returns_zero(self) -> None:
        """Negative costs are treated as absent (0.0)."""
        meta = json.dumps({COST_METADATA_KEY: -0.5})
        assert extract_node_cost(meta) == 0.0

    def test_string_cost_parsed(self) -> None:
        """String-formatted cost values are parsed to float."""
        meta = json.dumps({COST_METADATA_KEY: "0.2345"})
        assert extract_node_cost(meta) == pytest.approx(0.2345)

    def test_non_numeric_cost_returns_zero(self) -> None:
        meta = json.dumps({COST_METADATA_KEY: "not-a-number"})
        assert extract_node_cost(meta) == 0.0

    def test_cost_never_returns_placeholder(self) -> None:
        """Confirm the function returns actual value, never 0.01 placeholder."""
        meta_zero = json.dumps({})
        meta_real = json.dumps({COST_METADATA_KEY: 2.5678})
        assert extract_node_cost(meta_zero) == 0.0  # never 0.01
        assert extract_node_cost(meta_real) == pytest.approx(2.5678)  # actual value


class TestCostAggregation:
    """Tests for _enrich_costs() — post-order cost aggregation (D4)."""

    def _make_tree_node(
        self,
        run_id: str = "node-1",
        cost_usd: float = 0.0,
        children: list[TreeNode] | None = None,
    ) -> TreeNode:
        """Helper to build a TreeNode with specific cost metadata."""
        meta = {}
        if cost_usd > 0:
            meta[COST_METADATA_KEY] = cost_usd
        return TreeNode(
            run_id=run_id,
            parent_run_id=None,
            name="test-node",
            display_name="test-node",
            node_type="graph_node",
            status="success",
            start_time="2026-03-28T10:00:00",
            end_time="2026-03-28T10:05:00",
            cost=0.0,
            duration_seconds=0.0,
            model="",
            inputs_json=None,
            outputs_json=None,
            metadata_json=json.dumps(meta) if meta else "{}",
            error=None,
            created_at="2026-03-28T10:00:00",
            children=children or [],
        )

    def test_leaf_node_gets_own_cost(self) -> None:
        """A leaf node's cost comes from its own metadata_json."""
        leaf = self._make_tree_node(cost_usd=FIXTURE_COST_A)
        _enrich_costs([leaf])
        assert leaf.cost == pytest.approx(FIXTURE_COST_A)

    def test_leaf_without_cost_is_zero(self) -> None:
        """A leaf with no cost data shows 0.0, not 0.01."""
        leaf = self._make_tree_node(cost_usd=0.0)
        _enrich_costs([leaf])
        assert leaf.cost == 0.0

    def test_parent_aggregates_children_costs(self) -> None:
        """Parent cost = sum of all children costs."""
        child_a = self._make_tree_node(run_id="child-a", cost_usd=FIXTURE_COST_A)
        child_b = self._make_tree_node(run_id="child-b", cost_usd=FIXTURE_COST_B)
        parent = self._make_tree_node(run_id="parent", children=[child_a, child_b])
        _enrich_costs([parent])
        expected = FIXTURE_COST_A + FIXTURE_COST_B
        assert parent.cost == pytest.approx(expected)

    def test_three_level_aggregation(self) -> None:
        """Grandchild costs roll up through child to parent."""
        grandchild = self._make_tree_node(run_id="gc", cost_usd=FIXTURE_COST_C)
        child = self._make_tree_node(run_id="child", cost_usd=FIXTURE_COST_A, children=[grandchild])
        parent = self._make_tree_node(run_id="parent", children=[child])
        _enrich_costs([parent])
        # grandchild.cost = FIXTURE_COST_C
        assert grandchild.cost == pytest.approx(FIXTURE_COST_C)
        # child.cost = own + grandchild = FIXTURE_COST_A + FIXTURE_COST_C
        assert child.cost == pytest.approx(FIXTURE_COST_A + FIXTURE_COST_C)
        # parent.cost = child.cost (parent has no own cost)
        assert parent.cost == pytest.approx(FIXTURE_COST_A + FIXTURE_COST_C)

    def test_no_placeholder_values(self) -> None:
        """No node in the tree ever gets 0.01 as a cost (AC45)."""
        child_no_cost = self._make_tree_node(run_id="c1")
        child_with_cost = self._make_tree_node(run_id="c2", cost_usd=FIXTURE_COST_B)
        parent = self._make_tree_node(run_id="parent", children=[child_no_cost, child_with_cost])
        _enrich_costs([parent])
        assert child_no_cost.cost == 0.0  # not 0.01
        assert child_with_cost.cost == pytest.approx(FIXTURE_COST_B)
        assert parent.cost == pytest.approx(FIXTURE_COST_B)

    def test_multiple_top_level_nodes(self) -> None:
        """Multiple top-level nodes are each enriched independently."""
        node_a = self._make_tree_node(run_id="a", cost_usd=FIXTURE_COST_A)
        node_b = self._make_tree_node(run_id="b", cost_usd=FIXTURE_COST_B)
        _enrich_costs([node_a, node_b])
        assert node_a.cost == pytest.approx(FIXTURE_COST_A)
        assert node_b.cost == pytest.approx(FIXTURE_COST_B)


class TestCostIntegrationInBuildTree:
    """Tests that build_tree() produces trees with correct cost values (D4)."""

    def test_build_tree_leaf_cost(self) -> None:
        """Leaf nodes in build_tree output have their own cost from metadata."""
        rows = [
            _make_row(
                run_id=FIXTURE_CHILD_A_ID,
                parent_run_id=FIXTURE_ROOT_ID,
                name="Read",
                metadata={COST_METADATA_KEY: FIXTURE_COST_A},
            ),
        ]
        result = build_tree(FIXTURE_ROOT_ID, rows)
        assert len(result) == 1
        assert result[0].cost == pytest.approx(FIXTURE_COST_A)

    def test_build_tree_parent_aggregates(self) -> None:
        """Parent nodes aggregate child costs in build_tree output."""
        rows = [
            _make_row(
                run_id=FIXTURE_CHILD_A_ID,
                parent_run_id=FIXTURE_ROOT_ID,
                name="execute_plan",
            ),
            _make_row(
                run_id=FIXTURE_GRANDCHILD_ID,
                parent_run_id=FIXTURE_CHILD_A_ID,
                name="Read",
                metadata={COST_METADATA_KEY: FIXTURE_COST_B},
            ),
        ]
        result = build_tree(FIXTURE_ROOT_ID, rows)
        parent = result[0]
        assert parent.cost == pytest.approx(FIXTURE_COST_B)
        assert parent.children[0].cost == pytest.approx(FIXTURE_COST_B)

    def test_build_tree_no_cost_nodes_show_zero(self) -> None:
        """Nodes without cost data show 0.0, never 0.01 (AC5, AC45)."""
        rows = [
            _make_row(
                run_id=FIXTURE_CHILD_A_ID,
                parent_run_id=FIXTURE_ROOT_ID,
                name="intake",
            ),
        ]
        result = build_tree(FIXTURE_ROOT_ID, rows)
        assert result[0].cost == 0.0


# ─── D5: Duration Computation tests ─────────────────────────────────────────


# Timestamps for duration tests: a 5-minute window
FIXTURE_DURATION_START = "2026-03-28T10:00:00"
FIXTURE_DURATION_END = "2026-03-28T10:05:00"
FIXTURE_DURATION_SECONDS = 300.0  # 5 minutes

# Near-zero dispatch: 0.01s apart
FIXTURE_NEAR_ZERO_START = "2026-03-28T10:00:00.000000"
FIXTURE_NEAR_ZERO_END = "2026-03-28T10:00:00.010000"
FIXTURE_NEAR_ZERO_SECONDS = 0.01

# Descendant spans: agent ran from 10:00:30 to 10:04:30
FIXTURE_DESC_START = "2026-03-28T10:00:30"
FIXTURE_DESC_END = "2026-03-28T10:04:30"
FIXTURE_DESC_SPAN_SECONDS = 240.0  # 4 minutes


class TestParseTimestamp:
    """Tests for _parse_timestamp() helper."""

    def test_standard_format(self) -> None:
        result = _parse_timestamp("2026-03-28T10:00:00")
        assert result is not None
        assert result.hour == 10

    def test_microsecond_format(self) -> None:
        result = _parse_timestamp("2026-03-28T10:00:00.123456")
        assert result is not None
        assert result.microsecond == 123456

    def test_none_returns_none(self) -> None:
        assert _parse_timestamp(None) is None

    def test_empty_returns_none(self) -> None:
        assert _parse_timestamp("") is None

    def test_invalid_returns_none(self) -> None:
        assert _parse_timestamp("not-a-timestamp") is None


class TestComputeOwnDuration:
    """Tests for _compute_own_duration()."""

    def test_valid_five_minute_duration(self) -> None:
        result = _compute_own_duration(FIXTURE_DURATION_START, FIXTURE_DURATION_END)
        assert result == pytest.approx(FIXTURE_DURATION_SECONDS)

    def test_near_zero_duration(self) -> None:
        result = _compute_own_duration(FIXTURE_NEAR_ZERO_START, FIXTURE_NEAR_ZERO_END)
        assert result == pytest.approx(FIXTURE_NEAR_ZERO_SECONDS)

    def test_missing_start(self) -> None:
        assert _compute_own_duration(None, FIXTURE_DURATION_END) == 0.0

    def test_missing_end(self) -> None:
        assert _compute_own_duration(FIXTURE_DURATION_START, None) == 0.0

    def test_both_missing(self) -> None:
        assert _compute_own_duration(None, None) == 0.0

    def test_negative_delta_returns_zero(self) -> None:
        """If end < start (malformed data), return 0.0."""
        result = _compute_own_duration(FIXTURE_DURATION_END, FIXTURE_DURATION_START)
        assert result == 0.0


class TestDurationEnrichment:
    """Tests for _enrich_durations() — wall-clock duration with near-zero replacement (D5)."""

    def _make_tree_node(
        self,
        run_id: str = "node-1",
        start_time: str | None = FIXTURE_DURATION_START,
        end_time: str | None = FIXTURE_DURATION_END,
        children: list[TreeNode] | None = None,
    ) -> TreeNode:
        """Helper to build a TreeNode with specific timestamps."""
        return TreeNode(
            run_id=run_id,
            parent_run_id=None,
            name="test-node",
            display_name="test-node",
            node_type="graph_node",
            status="success",
            start_time=start_time,
            end_time=end_time,
            cost=0.0,
            duration_seconds=0.0,
            model="",
            inputs_json=None,
            outputs_json=None,
            metadata_json="{}",
            error=None,
            created_at="2026-03-28T10:00:00",
            children=children or [],
        )

    def test_leaf_with_valid_duration(self) -> None:
        """A leaf node with good timestamps uses its own duration."""
        leaf = self._make_tree_node(
            start_time=FIXTURE_DURATION_START,
            end_time=FIXTURE_DURATION_END,
        )
        _enrich_durations([leaf])
        assert leaf.duration_seconds == pytest.approx(FIXTURE_DURATION_SECONDS)

    def test_leaf_near_zero_stays_near_zero(self) -> None:
        """A leaf with near-zero duration keeps it (no children to fall back to)."""
        leaf = self._make_tree_node(
            start_time=FIXTURE_NEAR_ZERO_START,
            end_time=FIXTURE_NEAR_ZERO_END,
        )
        _enrich_durations([leaf])
        assert leaf.duration_seconds == pytest.approx(FIXTURE_NEAR_ZERO_SECONDS)

    def test_parent_near_zero_replaced_by_descendant_span(self) -> None:
        """A parent with near-zero own duration gets the descendant time span (AC47, AC48)."""
        child = self._make_tree_node(
            run_id="child",
            start_time=FIXTURE_DESC_START,
            end_time=FIXTURE_DESC_END,
        )
        parent = self._make_tree_node(
            run_id="parent",
            start_time=FIXTURE_NEAR_ZERO_START,
            end_time=FIXTURE_NEAR_ZERO_END,
            children=[child],
        )
        _enrich_durations([parent])
        # Parent should use descendant span, not its own 0.01s
        # Earliest = parent near-zero start, latest = child end
        # But since parent start is 10:00:00.000 and child end is 10:04:30,
        # span = 270 seconds
        assert parent.duration_seconds > NEAR_ZERO_DURATION_THRESHOLD_SECONDS
        # Child keeps its own good duration
        assert child.duration_seconds == pytest.approx(FIXTURE_DESC_SPAN_SECONDS)

    def test_parent_valid_duration_not_replaced(self) -> None:
        """A parent with >= 1.0s own duration keeps it unchanged."""
        child = self._make_tree_node(
            run_id="child",
            start_time="2026-03-28T10:01:00",
            end_time="2026-03-28T10:03:00",
        )
        parent = self._make_tree_node(
            run_id="parent",
            start_time=FIXTURE_DURATION_START,
            end_time=FIXTURE_DURATION_END,
            children=[child],
        )
        _enrich_durations([parent])
        assert parent.duration_seconds == pytest.approx(FIXTURE_DURATION_SECONDS)

    def test_multi_minute_phase_shows_real_minutes(self) -> None:
        """A phase that took minutes shows real wall-clock duration (AC7, AC49)."""
        # Phase dispatch: near-zero (0.01s)
        # Child agent ran for 3 minutes
        agent = self._make_tree_node(
            run_id="agent",
            start_time="2026-03-28T10:00:05",
            end_time="2026-03-28T10:03:05",
        )
        phase = self._make_tree_node(
            run_id="phase",
            start_time=FIXTURE_NEAR_ZERO_START,
            end_time=FIXTURE_NEAR_ZERO_END,
            children=[agent],
        )
        _enrich_durations([phase])
        # Phase should show ~3 minutes (180s), not 0.01s
        # Bounds: earliest=phase.start (10:00:00.000), latest=agent.end (10:03:05)
        assert phase.duration_seconds >= 180.0
        assert phase.duration_seconds < 200.0

    def test_no_timestamps_returns_zero(self) -> None:
        """Node with no timestamps gets 0.0 duration."""
        node = self._make_tree_node(start_time=None, end_time=None)
        _enrich_durations([node])
        assert node.duration_seconds == 0.0

    def test_deep_tree_descendant_bounds(self) -> None:
        """Descendant bounds collect from all levels, not just direct children."""
        # grandchild ends latest
        grandchild = self._make_tree_node(
            run_id="gc",
            start_time="2026-03-28T10:00:10",
            end_time="2026-03-28T10:07:00",  # 7 minutes in
        )
        child = self._make_tree_node(
            run_id="child",
            start_time="2026-03-28T10:00:05",
            end_time="2026-03-28T10:00:06",  # near-zero own
            children=[grandchild],
        )
        root = self._make_tree_node(
            run_id="root",
            start_time=FIXTURE_NEAR_ZERO_START,
            end_time=FIXTURE_NEAR_ZERO_END,
            children=[child],
        )
        _enrich_durations([root])
        # Root should span from its own start (10:00:00) to grandchild end (10:07:00)
        assert root.duration_seconds == pytest.approx(420.0)  # 7 minutes


class TestCollectTimeBounds:
    """Tests for _collect_time_bounds() helper."""

    def _make_node(
        self,
        start: str | None = None,
        end: str | None = None,
        children: list[TreeNode] | None = None,
    ) -> TreeNode:
        return TreeNode(
            run_id="n",
            parent_run_id=None,
            name="n",
            display_name="n",
            node_type="graph_node",
            status="success",
            start_time=start,
            end_time=end,
            cost=0.0,
            duration_seconds=0.0,
            model="",
            inputs_json=None,
            outputs_json=None,
            metadata_json="{}",
            error=None,
            created_at="",
            children=children or [],
        )

    def test_single_node_with_timestamps(self) -> None:
        node = self._make_node(start=FIXTURE_DURATION_START, end=FIXTURE_DURATION_END)
        earliest, latest = _collect_time_bounds(node)
        assert earliest is not None
        assert latest is not None
        assert earliest.hour == 10
        assert latest.minute == 5

    def test_single_node_no_timestamps(self) -> None:
        node = self._make_node()
        earliest, latest = _collect_time_bounds(node)
        assert earliest is None
        assert latest is None

    def test_child_extends_bounds(self) -> None:
        """Child with later end extends the latest bound."""
        child = self._make_node(
            start="2026-03-28T10:01:00",
            end="2026-03-28T10:10:00",  # later than parent
        )
        parent = self._make_node(
            start="2026-03-28T10:00:00",
            end="2026-03-28T10:05:00",
            children=[child],
        )
        earliest, latest = _collect_time_bounds(parent)
        assert earliest is not None
        assert latest is not None
        # Earliest = parent start (10:00)
        assert earliest.minute == 0
        # Latest = child end (10:10)
        assert latest.minute == 10


class TestDurationIntegrationInBuildTree:
    """Tests that build_tree() produces trees with correct duration values (D5)."""

    def test_build_tree_leaf_duration(self) -> None:
        """Leaf nodes in build_tree output have correct duration from timestamps."""
        rows = [
            _make_row(
                run_id=FIXTURE_CHILD_A_ID,
                parent_run_id=FIXTURE_ROOT_ID,
                name="Read",
                start_time=FIXTURE_DURATION_START,
                end_time=FIXTURE_DURATION_END,
            ),
        ]
        result = build_tree(FIXTURE_ROOT_ID, rows)
        assert result[0].duration_seconds == pytest.approx(FIXTURE_DURATION_SECONDS)

    def test_build_tree_near_zero_parent_replaced(self) -> None:
        """Parent with near-zero dispatch time gets descendant span in build_tree."""
        rows = [
            _make_row(
                run_id=FIXTURE_CHILD_A_ID,
                parent_run_id=FIXTURE_ROOT_ID,
                name="execute_plan",
                start_time=FIXTURE_NEAR_ZERO_START,
                end_time=FIXTURE_NEAR_ZERO_END,
            ),
            _make_row(
                run_id=FIXTURE_GRANDCHILD_ID,
                parent_run_id=FIXTURE_CHILD_A_ID,
                name="coder-agent",
                start_time=FIXTURE_DESC_START,
                end_time=FIXTURE_DESC_END,
            ),
        ]
        result = build_tree(FIXTURE_ROOT_ID, rows)
        parent = result[0]
        # Parent dispatch was 0.01s, but child ran 10:00:30-10:04:30
        # Descendant span: parent start (10:00:00) to child end (10:04:30) = 270s
        assert parent.duration_seconds > NEAR_ZERO_DURATION_THRESHOLD_SECONDS
        # Child has its own valid duration: 240s
        assert parent.children[0].duration_seconds == pytest.approx(FIXTURE_DESC_SPAN_SECONDS)
