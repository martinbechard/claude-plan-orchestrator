# langgraph_pipeline/shared/langsmith.py
# LangSmith tracing configuration and trace helper utilities.
# Design: docs/plans/2026-02-26-06-langsmith-observability-design.md

"""LangSmith observability: configure tracing, filter noisy nodes, attach metadata."""

import logging
import os
from typing import Any

from langgraph_pipeline.shared.config import load_orchestrator_config

# ─── Constants ────────────────────────────────────────────────────────────────

ENV_LANGCHAIN_API_KEY = "LANGCHAIN_API_KEY"
ENV_LANGCHAIN_TRACING_V2 = "LANGCHAIN_TRACING_V2"
ENV_LANGCHAIN_PROJECT = "LANGCHAIN_PROJECT"
ENV_LANGCHAIN_ENDPOINT = "LANGCHAIN_ENDPOINT"

DEFAULT_LANGSMITH_PROJECT = "claude-plan-orchestrator"
TRACING_ENABLED_VALUE = "true"

# Node names that produce high-frequency runs with no meaningful signal.
# should_trace() returns False for these to suppress custom metadata emission.
NOISY_NODE_NAMES = frozenset({"scan_backlog", "sleep", "wait"})

logger = logging.getLogger(__name__)


# ─── Public API ───────────────────────────────────────────────────────────────


def configure_tracing() -> bool:
    """Configure LangSmith tracing via LangChain environment variables.

    Reads configuration from (in priority order):
      1. Environment variables (LANGCHAIN_API_KEY already set)
      2. .claude/orchestrator-config.yaml langsmith section
      3. Defaults (tracing disabled when no API key)

    Sets LANGCHAIN_TRACING_V2, LANGCHAIN_PROJECT, and optionally
    LANGCHAIN_ENDPOINT when an API key is available.

    Returns:
        True if tracing was enabled, False if disabled (no API key).
    """
    api_key = _resolve_api_key()
    if not api_key:
        logger.warning(
            "LangSmith tracing disabled: LANGCHAIN_API_KEY not set "
            "and not found in orchestrator-config.yaml langsmith section."
        )
        return False

    os.environ[ENV_LANGCHAIN_API_KEY] = api_key
    os.environ[ENV_LANGCHAIN_TRACING_V2] = TRACING_ENABLED_VALUE
    os.environ[ENV_LANGCHAIN_PROJECT] = _resolve_project_name()

    endpoint = _resolve_endpoint()
    if endpoint:
        os.environ[ENV_LANGCHAIN_ENDPOINT] = endpoint

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
    """Return the LangSmith API key, preferring env var over config file."""
    env_key = os.environ.get(ENV_LANGCHAIN_API_KEY, "")
    if env_key:
        return env_key
    config = load_orchestrator_config()
    return config.get("langsmith", {}).get("api_key", "")


def _resolve_project_name() -> str:
    """Return the LangSmith project name from env, config, or default."""
    env_project = os.environ.get(ENV_LANGCHAIN_PROJECT, "")
    if env_project:
        return env_project
    config = load_orchestrator_config()
    return config.get("langsmith", {}).get("project", DEFAULT_LANGSMITH_PROJECT)


def _resolve_endpoint() -> str:
    """Return the optional LangSmith endpoint override, or empty string."""
    env_endpoint = os.environ.get(ENV_LANGCHAIN_ENDPOINT, "")
    if env_endpoint:
        return env_endpoint
    config = load_orchestrator_config()
    return config.get("langsmith", {}).get("endpoint", "")
