# langgraph_pipeline/shared/langsmith.py
# LangSmith tracing configuration and trace helper utilities.
# Design: docs/plans/2026-02-26-06-langsmith-observability-design.md

"""LangSmith observability: configure tracing, filter noisy nodes, attach metadata."""

import logging
import os
from typing import Any

from langgraph_pipeline.shared.config import load_orchestrator_config

# ─── Constants ────────────────────────────────────────────────────────────────

ENV_LANGSMITH_API_KEY = "LANGSMITH_API_KEY"
ENV_LANGSMITH_TRACING = "LANGCHAIN_TRACING_V2"
ENV_LANGSMITH_PROJECT = "LANGCHAIN_PROJECT"
ENV_LANGSMITH_ENDPOINT = "LANGCHAIN_ENDPOINT"
ENV_LANGSMITH_WORKSPACE_ID = "LANGSMITH_WORKSPACE_ID"

DEFAULT_LANGSMITH_PROJECT = "claude-plan-orchestrator"
TRACING_ENABLED_VALUE = "true"

# Node names that produce high-frequency runs with no meaningful signal.
# should_trace() returns False for these to suppress custom metadata emission.
NOISY_NODE_NAMES = frozenset({"scan_backlog", "sleep", "wait"})

logger = logging.getLogger(__name__)


# ─── Public API ───────────────────────────────────────────────────────────────


def configure_tracing() -> bool:
    """Configure LangSmith tracing via environment variables.

    Reads configuration from (in priority order):
      1. LANGSMITH_API_KEY environment variable
      2. .claude/orchestrator-config.yaml langsmith.api_key
      3. Defaults (tracing disabled when no API key)

    Sets LANGSMITH_API_KEY, LANGCHAIN_TRACING_V2, LANGCHAIN_PROJECT,
    and optionally LANGCHAIN_ENDPOINT when an API key is available.

    Returns:
        True if tracing was enabled, False if disabled (no API key).
    """
    api_key = _resolve_api_key()
    if not api_key:
        logger.warning(
            "LangSmith tracing disabled: LANGSMITH_API_KEY not set "
            "and not found in orchestrator-config.yaml langsmith.api_key. "
            "Get a free key at https://smith.langchain.com/settings/api-keys"
        )
        return False

    os.environ[ENV_LANGSMITH_API_KEY] = api_key
    os.environ[ENV_LANGSMITH_TRACING] = TRACING_ENABLED_VALUE
    os.environ[ENV_LANGSMITH_PROJECT] = _resolve_project_name()

    workspace_id = _resolve_workspace_id()
    if workspace_id:
        os.environ[ENV_LANGSMITH_WORKSPACE_ID] = workspace_id

    endpoint = _resolve_endpoint()
    if endpoint:
        os.environ[ENV_LANGSMITH_ENDPOINT] = endpoint

    return True


def should_trace(node_name: str) -> bool:
    """Return whether custom trace metadata should be emitted for this node.

    Returns False for high-frequency noisy nodes that produce no useful signal
    (e.g. scan_backlog polling iterations that found no items, sleep/wait cycles).
    LangGraph still records the node run; only custom metadata emission is skipped.

    Args:
        node_name: The graph node name being evaluated.

    Returns:
        True if metadata should be emitted, False to suppress emission.
    """
    return node_name not in NOISY_NODE_NAMES


def add_trace_metadata(metadata: dict[str, Any]) -> None:
    """Attach custom key-value metadata to the current LangSmith run.

    Intended for enriching traces with node name, graph level, cost, and token
    counts. Degrades gracefully when the langsmith package is not installed or
    when no active run context exists.

    Args:
        metadata: Dict of metadata to attach (e.g. node_name, graph_level,
            total_cost_usd, input_tokens, output_tokens, model).
    """
    try:
        from langsmith import run_trees  # type: ignore[import]

        current_run = run_trees.get_current_run_tree()
        if current_run is not None:
            current_run.add_metadata(metadata)
    except ImportError:
        pass  # langsmith package not installed -- degrade silently
    except Exception as exc:  # noqa: BLE001
        logger.debug("add_trace_metadata failed (non-fatal): %s", exc)


# ─── Private helpers ──────────────────────────────────────────────────────────


def _resolve_api_key() -> str:
    """Return the LangSmith API key from env var or config file."""
    env_key = os.environ.get(ENV_LANGSMITH_API_KEY, "")
    if env_key:
        return env_key
    config = load_orchestrator_config()
    return config.get("langsmith", {}).get("api_key", "")


def _resolve_project_name() -> str:
    """Return the LangSmith project name from env, config, or default."""
    env_project = os.environ.get(ENV_LANGSMITH_PROJECT, "")
    if env_project:
        return env_project
    config = load_orchestrator_config()
    return config.get("langsmith", {}).get("project", DEFAULT_LANGSMITH_PROJECT)


def _resolve_workspace_id() -> str:
    """Return the LangSmith workspace ID for org-scoped service keys."""
    env_ws = os.environ.get(ENV_LANGSMITH_WORKSPACE_ID, "")
    if env_ws:
        return env_ws
    config = load_orchestrator_config()
    return config.get("langsmith", {}).get("workspace_id", "")


def _resolve_endpoint() -> str:
    """Return the optional LangSmith endpoint override, or empty string."""
    env_endpoint = os.environ.get(ENV_LANGSMITH_ENDPOINT, "")
    if env_endpoint:
        return env_endpoint
    config = load_orchestrator_config()
    return config.get("langsmith", {}).get("endpoint", "")
