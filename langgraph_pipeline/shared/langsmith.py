# langgraph_pipeline/shared/langsmith.py
# LangSmith tracing configuration and trace helper utilities.
# Design: docs/plans/2026-02-26-06-langsmith-observability-design.md

"""LangSmith observability: configure tracing, filter noisy nodes, attach metadata.

Tracing is opt-in via the langsmith.enabled config flag or --no-tracing CLI flag.
When enabled, both LANGSMITH_API_KEY and LANGSMITH_WORKSPACE_ID must be set
(via .env.local, environment variables, or orchestrator-config.yaml).
"""

import logging
import os
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from langgraph_pipeline.shared.config import load_orchestrator_config

if TYPE_CHECKING:
    from langgraph_pipeline.shared.claude_cli import ToolCallRecord

# ─── Constants ────────────────────────────────────────────────────────────────

ENV_LANGSMITH_API_KEY = "LANGSMITH_API_KEY"
ENV_LANGSMITH_TRACING = "LANGCHAIN_TRACING_V2"
ENV_LANGSMITH_PROJECT = "LANGCHAIN_PROJECT"
ENV_LANGSMITH_ENDPOINT = "LANGCHAIN_ENDPOINT"
ENV_LANGSMITH_WORKSPACE_ID = "LANGSMITH_WORKSPACE_ID"

DEFAULT_LANGSMITH_PROJECT = "claude-plan-orchestrator"
TRACING_ENABLED_VALUE = "true"
TRACING_DISABLED_VALUE = "false"

# Node names that produce high-frequency runs with no meaningful signal.
# should_trace() returns False for these to suppress custom metadata emission.
NOISY_NODE_NAMES = frozenset({"scan_backlog", "sleep", "wait"})

logger = logging.getLogger(__name__)

# Module-level flag to avoid repeated warnings across multiple configure_tracing() calls.
_tracing_configured = False
_tracing_active = False


# ─── Public API ───────────────────────────────────────────────────────────────


def configure_tracing() -> bool:
    """Configure LangSmith tracing if enabled and credentials are valid.

    This function is idempotent: the first call resolves configuration and
    logs any warnings; subsequent calls return the cached result silently.

    Tracing is enabled when langsmith.enabled is true in orchestrator-config.yaml
    (or not explicitly disabled via --no-tracing). When enabled, both
    LANGSMITH_API_KEY and LANGSMITH_WORKSPACE_ID must be present.

    Resolution order for each setting:
      1. Environment variable (including .env.local)
      2. orchestrator-config.yaml langsmith section

    Returns:
        True if tracing was enabled, False if disabled or misconfigured.
    """
    global _tracing_configured, _tracing_active

    if _tracing_configured:
        return _tracing_active

    _tracing_configured = True
    _tracing_active = False

    config = load_orchestrator_config()
    langsmith_config = config.get("langsmith", {})

    # Check the enabled flag. Default to False (opt-in).
    enabled = langsmith_config.get("enabled", False)
    if not enabled:
        logger.info(
            "LangSmith tracing is not enabled. "
            "Set langsmith.enabled: true in orchestrator-config.yaml to enable."
        )
        # Explicitly disable tracing so LangGraph doesn't try to trace
        os.environ[ENV_LANGSMITH_TRACING] = TRACING_DISABLED_VALUE
        return False

    # Validate API key
    api_key = _resolve_value(ENV_LANGSMITH_API_KEY, langsmith_config, "api_key")
    if not api_key:
        logger.warning(
            "LangSmith enabled but LANGSMITH_API_KEY not set. "
            "Tracing disabled. Get a key at https://smith.langchain.com/settings/api-keys"
        )
        os.environ[ENV_LANGSMITH_TRACING] = TRACING_DISABLED_VALUE
        return False

    # Validate workspace ID
    workspace_id = _resolve_value(ENV_LANGSMITH_WORKSPACE_ID, langsmith_config, "workspace_id")
    if not workspace_id:
        logger.warning(
            "LangSmith enabled but LANGSMITH_WORKSPACE_ID not set. "
            "Tracing disabled. Find your workspace ID at "
            "https://smith.langchain.com (Settings > Workspace ID)."
        )
        os.environ[ENV_LANGSMITH_TRACING] = TRACING_DISABLED_VALUE
        return False

    # All validated -- activate tracing
    os.environ[ENV_LANGSMITH_API_KEY] = api_key
    os.environ[ENV_LANGSMITH_WORKSPACE_ID] = workspace_id
    os.environ[ENV_LANGSMITH_TRACING] = TRACING_ENABLED_VALUE
    os.environ[ENV_LANGSMITH_PROJECT] = _resolve_value(
        ENV_LANGSMITH_PROJECT, langsmith_config, "project"
    ) or DEFAULT_LANGSMITH_PROJECT

    endpoint = _resolve_value(ENV_LANGSMITH_ENDPOINT, langsmith_config, "endpoint")
    if endpoint:
        os.environ[ENV_LANGSMITH_ENDPOINT] = endpoint

    _tracing_active = True
    return True


def reset_tracing_state() -> None:
    """Reset the module-level tracing state. Used in tests only."""
    global _tracing_configured, _tracing_active
    _tracing_configured = False
    _tracing_active = False


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


def emit_tool_call_traces(
    tool_calls: "list[ToolCallRecord]",
    run_name: str,
    metadata: dict[str, Any],
) -> None:
    """Emit a LangSmith trace with child runs for each tool call.

    Creates a standalone RunTree (not attached to the graph's trace context)
    with one child run per ToolCallRecord. The parent run represents the
    task execution; children represent individual tool calls and text blocks.

    Degrades gracefully when langsmith is not installed or tracing is inactive.

    Args:
        tool_calls: Events collected by stream_json_output during task execution.
        run_name: Label for the parent run (e.g., "execute_task:1.1").
        metadata: Task-level metadata attached to each child run.
    """
    if not _tracing_active or not tool_calls:
        return
    try:
        from langsmith import RunTree  # type: ignore[import]

        parent = RunTree(
            name=run_name,
            run_type="chain",
            inputs={"task_metadata": metadata},
            extra={"metadata": metadata},
        )

        for record in tool_calls:
            is_tool = record["type"] == "tool_use"
            child = parent.create_child(
                name=record["tool_name"] if is_tool else "assistant_text",
                run_type="tool" if is_tool else "llm",
                inputs=record["tool_input"],
                extra={"metadata": {**metadata, "timestamp": record["timestamp"]}},
            )
            duration_s = record.get("duration_s")
            start_time = record.get("start_time")
            if duration_s is not None and start_time is not None:
                end_time = start_time + timedelta(seconds=duration_s)
                child.end(outputs=record["tool_input"], end_time=end_time)
            else:
                child.end(outputs=record["tool_input"])
            child.post()

        parent.end()
        parent.post()

    except ImportError:
        pass  # langsmith package not installed -- degrade silently
    except Exception as exc:
        logger.debug("emit_tool_call_traces failed (non-fatal): %s", exc)


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
        from langsmith.run_helpers import get_current_run_tree  # type: ignore[import]

        current_run = get_current_run_tree()
        if current_run is not None:
            current_run.add_metadata(metadata)
    except ImportError:
        pass  # langsmith package not installed -- degrade silently
    except Exception as exc:  # noqa: BLE001
        logger.debug("add_trace_metadata failed (non-fatal): %s", exc)


# ─── Private helpers ──────────────────────────────────────────────────────────


def _resolve_value(env_var: str, config_section: dict, config_key: str) -> str:
    """Return a value from env var first, then config file, or empty string."""
    env_val = os.environ.get(env_var, "")
    if env_val:
        return env_val
    return config_section.get(config_key, "")
