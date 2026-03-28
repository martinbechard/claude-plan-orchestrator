# langgraph_pipeline/web/helpers/execution_tree.py
# Assembles flat trace DB rows into a nested execution tree with display names.
# Design: docs/plans/2026-03-28-71-execution-history-redesign-design.md (D1, D2, D3)

"""Build a nested TreeNode tree from flat TracingProxy rows.

Public API:
    build_tree(root_run_id, flat_rows) -> list[TreeNode]
    resolve_display_name(row, children_rows) -> str

The tree construction includes:
- D1: Recursive nesting with no depth limit
- D2: Three-tier name resolution (metadata slug -> child span scan -> run_id prefix)
- D3: UI-level deduplication by run_id (keep most complete row)
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

# Node type classification keywords (checked in order, first match wins).
# More-specific patterns must come first.
_NODE_TYPE_PATTERNS: list[tuple[str, str]] = [
    ("tool_call", "tool_call"),
    ("read", "tool_call"),
    ("edit", "tool_call"),
    ("write", "tool_call"),
    ("bash", "tool_call"),
    ("grep", "tool_call"),
    ("glob", "tool_call"),
    ("skill", "tool_call"),
    ("todowrite", "tool_call"),
    ("webfetch", "tool_call"),
    ("websearch", "tool_call"),
    ("agent", "agent"),
    ("subgraph", "subgraph"),
]

NODE_TYPE_GRAPH = "graph_node"
NODE_TYPE_SUBGRAPH = "subgraph"
NODE_TYPE_AGENT = "agent"
NODE_TYPE_TOOL_CALL = "tool_call"

# Sentinel name from the LangGraph SDK that must never be shown to users.
_LANGGRAPH_DEFAULT_NAME = "LangGraph"

# Prefix length for run_id fallback display name (first 8 hex chars).
_RUN_ID_PREFIX_LENGTH = 8


# ─── Data Types ───────────────────────────────────────────────────────────────


@dataclass
class TreeNode:
    """A single node in the execution tree.

    Each node corresponds to one trace row and may contain nested children.
    The node_type field classifies the node for UI rendering (badges, icons).
    """

    run_id: str
    parent_run_id: Optional[str]
    name: str
    display_name: str
    node_type: str  # "graph_node" | "subgraph" | "agent" | "tool_call"
    status: str     # "success" | "error" | "running" | "unknown"
    start_time: Optional[str]
    end_time: Optional[str]
    model: str
    inputs_json: Optional[str]
    outputs_json: Optional[str]
    metadata_json: Optional[str]
    error: Optional[str]
    created_at: str
    children: list["TreeNode"] = field(default_factory=list)


# ─── Public API ───────────────────────────────────────────────────────────────


def build_tree(root_run_id: str, flat_rows: list[dict]) -> list["TreeNode"]:
    """Assemble flat DB rows into a nested tree of TreeNode objects.

    Performs D3 deduplication first (by run_id, keeping most complete row),
    then builds parent->children relationships, classifies node types,
    and resolves display names (D2 three-tier fallback).

    Args:
        root_run_id: The run_id of the root trace (not included in output).
        flat_rows: Flat list of descendant trace row dicts from get_full_tree().

    Returns:
        List of top-level TreeNode children of root_run_id, each with nested
        children populated recursively.
    """
    deduped = _deduplicate_rows(flat_rows)

    # Index rows by run_id and group by parent_run_id
    rows_by_id: dict[str, dict] = {}
    children_by_parent: dict[str, list[dict]] = {}
    for row in deduped:
        rid = row.get("run_id", "")
        if not rid:
            continue
        rows_by_id[rid] = row
        parent = row.get("parent_run_id") or ""
        children_by_parent.setdefault(parent, []).append(row)

    # Build tree recursively starting from root's direct children
    top_level_rows = children_by_parent.get(root_run_id, [])
    return [
        _build_node(row, children_by_parent)
        for row in top_level_rows
    ]


def resolve_display_name(
    row: dict,
    children_rows: Optional[list[dict]] = None,
) -> str:
    """Resolve a human-readable display name for a trace row.

    Three-tier fallback chain (D2):
    1. Metadata slug: metadata_json.item_slug or metadata_json.slug
    2. Child span scan: first non-empty slug in children's metadata
    3. Run ID prefix: first 8 characters of run_id

    The name "LangGraph" (the SDK default) is never returned.

    Args:
        row: A trace row dict with at least run_id, name, metadata_json.
        children_rows: Optional list of direct children row dicts for tier-2 lookup.

    Returns:
        A non-empty display name string.
    """
    # Tier 0: use the row's own name if it's not the LangGraph sentinel
    raw_name = row.get("name", "")
    if raw_name and raw_name != _LANGGRAPH_DEFAULT_NAME:
        return raw_name

    # Tier 1: metadata slug
    meta = _parse_json(row.get("metadata_json"))
    slug = meta.get("item_slug") or meta.get("slug") or ""
    if slug and slug != _LANGGRAPH_DEFAULT_NAME:
        return slug

    # Tier 2: scan children metadata for slug
    if children_rows:
        for child in children_rows:
            child_meta = _parse_json(child.get("metadata_json"))
            child_slug = child_meta.get("item_slug") or child_meta.get("slug") or ""
            if child_slug and child_slug != _LANGGRAPH_DEFAULT_NAME:
                return child_slug

    # Tier 3: run_id prefix
    run_id = row.get("run_id", "")
    if run_id:
        return run_id[:_RUN_ID_PREFIX_LENGTH]

    return "unknown"


def classify_node_type(name: str, row: dict) -> str:
    """Classify a trace row into a node type for UI rendering.

    Uses the row name and metadata to determine if this is a graph_node,
    subgraph, agent session, or tool_call.

    Args:
        name: The run name (lowercase checked against patterns).
        row: The full trace row dict for metadata inspection.

    Returns:
        One of: "graph_node", "subgraph", "agent", "tool_call".
    """
    lower_name = name.lower()

    # Check metadata for explicit node type hints
    meta = _parse_json(row.get("metadata_json"))
    explicit_type = meta.get("node_type") or meta.get("run_type") or ""
    if explicit_type:
        lower_explicit = explicit_type.lower()
        if lower_explicit in (NODE_TYPE_TOOL_CALL, "tool"):
            return NODE_TYPE_TOOL_CALL
        if lower_explicit in (NODE_TYPE_AGENT, "llm", "chat_model"):
            return NODE_TYPE_AGENT
        if lower_explicit in (NODE_TYPE_SUBGRAPH,):
            return NODE_TYPE_SUBGRAPH

    # Pattern-match on the run name
    for pattern, node_type in _NODE_TYPE_PATTERNS:
        if pattern in lower_name:
            return node_type

    # If the row has a model set, it's likely an agent/LLM invocation
    model = row.get("model", "")
    if model and model.strip():
        return NODE_TYPE_AGENT

    # Default to graph_node for pipeline-level nodes
    return NODE_TYPE_GRAPH


# ─── Internal Helpers ─────────────────────────────────────────────────────────


def _build_node(row: dict, children_by_parent: dict[str, list[dict]]) -> TreeNode:
    """Recursively build a TreeNode from a row dict and its children lookup."""
    run_id = row.get("run_id", "")
    name = row.get("name", "")

    # Get direct children rows for name resolution and recursive build
    child_rows = children_by_parent.get(run_id, [])

    display_name = resolve_display_name(row, child_rows)
    node_type = classify_node_type(name, row)
    status = _extract_status(row)

    children = [
        _build_node(child_row, children_by_parent)
        for child_row in child_rows
    ]

    return TreeNode(
        run_id=run_id,
        parent_run_id=row.get("parent_run_id"),
        name=name,
        display_name=display_name,
        node_type=node_type,
        status=status,
        start_time=row.get("start_time"),
        end_time=row.get("end_time"),
        model=row.get("model", ""),
        inputs_json=row.get("inputs_json"),
        outputs_json=row.get("outputs_json"),
        metadata_json=row.get("metadata_json"),
        error=row.get("error"),
        created_at=row.get("created_at", ""),
        children=children,
    )


def _deduplicate_rows(rows: list[dict]) -> list[dict]:
    """Deduplicate rows by run_id, keeping the most complete row (D3).

    When multiple rows share the same run_id (e.g. start and end events),
    prefer the row that has end_time populated.  If neither or both have
    end_time, keep the one with the latest created_at timestamp.

    Args:
        rows: Flat list of trace row dicts, possibly containing duplicates.

    Returns:
        Deduplicated list preserving original ordering of winners.
    """
    best: dict[str, dict] = {}
    order: list[str] = []

    for row in rows:
        rid = row.get("run_id", "")
        if not rid:
            continue

        if rid not in best:
            best[rid] = row
            order.append(rid)
        else:
            existing = best[rid]
            if _is_more_complete(row, existing):
                best[rid] = row

    return [best[rid] for rid in order]


def _is_more_complete(candidate: dict, existing: dict) -> bool:
    """Return True if candidate is more complete than existing.

    A row with end_time is preferred over one without.  When both have
    end_time (or neither does), the one with the later created_at wins.
    """
    candidate_has_end = bool(candidate.get("end_time"))
    existing_has_end = bool(existing.get("end_time"))

    if candidate_has_end and not existing_has_end:
        return True
    if existing_has_end and not candidate_has_end:
        return False

    # Both have end_time or neither does — prefer later created_at
    return (candidate.get("created_at") or "") > (existing.get("created_at") or "")


def _extract_status(row: dict) -> str:
    """Determine run status from row fields."""
    if row.get("error"):
        return "error"
    if row.get("end_time"):
        return "success"
    if row.get("start_time"):
        return "running"
    return "unknown"


def _parse_json(raw: Optional[str]) -> dict:
    """Parse a JSON string to a dict; return empty dict on any error."""
    if not raw:
        return {}
    try:
        result = json.loads(raw)
        return result if isinstance(result, dict) else {}
    except (ValueError, TypeError):
        return {}
