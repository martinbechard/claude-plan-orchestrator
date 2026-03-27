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
import re
import uuid
from datetime import timedelta
from typing import TYPE_CHECKING, Any, Optional

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

# Marker line written to item files to persist the root trace UUID across restarts.
LANGSMITH_TRACE_LINE_PREFIX = "## LangSmith Trace: "
LANGSMITH_TRACE_PATTERN = re.compile(
    r"^## LangSmith Trace: ([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$",
    re.MULTILINE,
)

logger = logging.getLogger(__name__)

# Module-level flag to avoid repeated warnings across multiple configure_tracing() calls.
_tracing_configured = False
_tracing_active = False


def _get_tracing_proxy() -> Any:
    """Return the active TracingProxy singleton, or None when unavailable.

    Uses a lazy import so the web module is not required when the proxy
    is not configured; any import error degrades silently to None.
    """
    try:
        from langgraph_pipeline.web.proxy import get_proxy  # type: ignore[import]

        return get_proxy()
    except Exception:
        return None


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

    # If the environment is already wired for a local proxy (e.g. inherited from
    # the supervisor process that called configure_tracing() first), trust it.
    # This covers worker subprocesses which share the parent's env vars but not
    # its in-memory module state.
    if (
        os.environ.get(ENV_LANGSMITH_TRACING) == TRACING_ENABLED_VALUE
        and os.environ.get(ENV_LANGSMITH_ENDPOINT, "").startswith("http://localhost")
    ):
        logger.debug(
            "configure_tracing: using inherited proxy endpoint %s",
            os.environ[ENV_LANGSMITH_ENDPOINT],
        )
        _tracing_active = True
        return True

    config = load_orchestrator_config()
    langsmith_config = config.get("langsmith", {})

    # If the local web server proxy is running, activate tracing and redirect
    # to it — regardless of langsmith.enabled.  Traces are captured locally
    # and only forwarded to LangSmith when forward_to_langsmith: true is set.
    try:
        from langgraph_pipeline.web.server import get_active_port
        local_port = get_active_port()
        if local_port is not None:
            os.environ[ENV_LANGSMITH_API_KEY] = os.environ.get(ENV_LANGSMITH_API_KEY, "local-proxy")
            os.environ[ENV_LANGSMITH_TRACING] = TRACING_ENABLED_VALUE
            os.environ[ENV_LANGSMITH_PROJECT] = _resolve_value(
                ENV_LANGSMITH_PROJECT, langsmith_config, "project"
            ) or DEFAULT_LANGSMITH_PROJECT
            os.environ[ENV_LANGSMITH_ENDPOINT] = f"http://localhost:{local_port}"
            logger.info(
                "LangSmith traces redirected to local proxy at http://localhost:%d "
                "(forward_to_langsmith=False by default)",
                local_port,
            )
            _tracing_active = True
            return True
    except Exception:
        pass

    # Check the enabled flag. Default to False (opt-in).
    enabled = langsmith_config.get("enabled", False)
    if not enabled:
        logger.info(
            "LangSmith tracing is not enabled. "
            "Set langsmith.enabled: true in orchestrator-config.yaml to enable, "
            "or start with --web to capture traces locally without consuming quota."
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
    parent_run_id: Optional[str] = None,
) -> None:
    """Emit a LangSmith trace with child runs for each tool call.

    Creates a RunTree with one child run per ToolCallRecord. The parent run
    represents the task execution; children represent individual tool calls and
    text blocks. When parent_run_id is provided the run is attached under the
    shared root trace for the work item.

    Degrades gracefully when langsmith is not installed or tracing is inactive.

    Args:
        tool_calls: Events collected by stream_json_output during task execution.
        run_name: Label for the parent run (e.g., "execute_task:1.1").
        metadata: Task-level metadata attached to each child run.
        parent_run_id: Optional UUID of the root RunTree to nest this run under.
    """
    if not _tracing_active or not tool_calls:
        return
    try:
        from langsmith import RunTree  # type: ignore[import]

        run_tree_kwargs: dict[str, Any] = {
            "name": run_name,
            "run_type": "chain",
            "inputs": {"task_metadata": metadata},
            "extra": {"metadata": metadata},
        }
        if parent_run_id is not None:
            run_tree_kwargs["parent_run_id"] = parent_run_id

        parent = RunTree(**run_tree_kwargs)

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
            child.post()  # routes to LANGCHAIN_ENDPOINT (local proxy when web is running)

        parent.end()
        parent.post()

    except ImportError:
        pass  # langsmith package not installed -- degrade silently
    except Exception as exc:
        logger.debug("emit_tool_call_traces failed (non-fatal): %s", exc)


def create_root_run(item_slug: str, item_path: str) -> tuple[Any, Optional[str]]:
    """Create or recover the shared root RunTree for a work item.

    Reads item_path for an existing "## LangSmith Trace: <uuid>" line.  If
    found, reconstructs the RunTree using that UUID so all subsequent spans are
    grouped under the same top-level trace.  If not found, creates a fresh
    RunTree, generates a UUID, and writes the marker line to item_path.

    Degrades silently when tracing is inactive or langsmith is not installed,
    returning (None, None) so callers can pass the UUID directly into state
    without a None-check.

    Args:
        item_slug: Human-readable name for the root run (e.g. "my-feature").
        item_path: Absolute path to the item markdown file.

    Returns:
        (run_tree, uuid_str) when tracing is active; (None, None) otherwise.
    """
    if not _tracing_active:
        return None, None
    try:
        from langsmith import RunTree  # type: ignore[import]

        existing_id = _read_trace_id_from_file(item_path)
        if existing_id:
            run_tree = RunTree(id=existing_id, name=item_slug, run_type="chain")
            trace_id = existing_id
        else:
            trace_id = str(uuid.uuid4())
            run_tree = RunTree(id=trace_id, name=item_slug, run_type="chain")
            _write_trace_id_to_file(item_path, trace_id)
            # Post immediately so the root run appears in the proxy DB as soon as the
            # worker starts — the dashboard trace link is non-empty from the first poll.
            run_tree.post()

        return run_tree, trace_id

    except ImportError:
        return None, None
    except Exception as exc:
        logger.debug("create_root_run failed (non-fatal): %s", exc)
        return None, None


def finalize_root_run(
    root_run_id: Optional[str], outputs: dict[str, Any], item_slug: str = ""
) -> None:
    """End and post the shared root RunTree for a completed work item.

    Reconstructs the RunTree by UUID, calls end() with the supplied outputs,
    then posts it to LangSmith so the trace is marked complete.

    Degrades silently when tracing is inactive, root_run_id is None, or
    langsmith is not installed.

    Args:
        root_run_id: UUID string returned by create_root_run, or None.
        outputs: Final outputs to attach (e.g. {"item_slug": slug, "outcome": "PASS"}).
        item_slug: Work item slug used as the RunTree name for readability in LangSmith.
            Falls back to "root" when empty so old traces remain unambiguous.
    """
    if not _tracing_active or not root_run_id:
        return
    try:
        from langsmith import RunTree  # type: ignore[import]

        run_name = item_slug if item_slug else "root"
        root_run = RunTree(id=root_run_id, name=run_name, run_type="chain")
        root_run.end(outputs=outputs)
        root_run.post()  # routes to LANGCHAIN_ENDPOINT (local proxy when web is running)

    except ImportError:
        pass
    except Exception as exc:
        logger.debug("finalize_root_run failed (non-fatal): %s", exc)


def read_trace_id_from_file(item_path: str) -> Optional[str]:
    """Return the LangSmith trace UUID from an item file, or None if absent.

    Public wrapper around _read_trace_id_from_file so supervisors can read
    the trace UUID from claimed item files without importing private helpers.

    Args:
        item_path: Absolute path to the item markdown file.

    Returns:
        UUID string if a trace marker line is present, None otherwise.
    """
    return _read_trace_id_from_file(item_path)


def add_trace_metadata(metadata: dict[str, Any]) -> None:
    """Attach custom key-value metadata to the current LangSmith run.

    Intended for enriching traces with node name, graph level, cost, and token
    counts. Uses two strategies:
    1. SDK: add_metadata on the in-memory RunTree (may not persist in newer SDK versions)
    2. Direct DB: merge metadata into the proxy DB row for this run_id

    Args:
        metadata: Dict of metadata to attach (e.g. node_name, graph_level,
            total_cost_usd, input_tokens, output_tokens, model).
    """
    run_id = None
    try:
        from langsmith.run_helpers import get_current_run_tree  # type: ignore[import]

        current_run = get_current_run_tree()
        if current_run is not None:
            current_run.add_metadata(metadata)
            run_id = str(current_run.id)
    except ImportError:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.debug("add_trace_metadata SDK call failed (non-fatal): %s", exc)

    # Also write directly to the proxy DB so metadata persists regardless of
    # SDK batching behavior (langsmith 0.7.22+ may not include add_metadata
    # additions in the multipart payload sent to the proxy).
    if run_id:
        try:
            from langgraph_pipeline.web.proxy import get_proxy
            proxy = get_proxy()
            if proxy is not None:
                proxy.merge_metadata(run_id, metadata)
        except Exception as exc:  # noqa: BLE001
            logger.debug("add_trace_metadata DB merge failed (non-fatal): %s", exc)


# ─── Private helpers ──────────────────────────────────────────────────────────


def _resolve_value(env_var: str, config_section: dict, config_key: str) -> str:
    """Return a value from env var first, then config file, or empty string."""
    env_val = os.environ.get(env_var, "")
    if env_val:
        return env_val
    return config_section.get(config_key, "")


def _read_trace_id_from_file(item_path: str) -> Optional[str]:
    """Return the LangSmith trace UUID from an item file, or None if absent."""
    try:
        with open(item_path) as f:
            content = f.read()
        match = LANGSMITH_TRACE_PATTERN.search(content)
        return match.group(1) if match else None
    except OSError:
        return None


def _write_trace_id_to_file(item_path: str, trace_id: str) -> None:
    """Write or update the LangSmith trace ID marker line in an item file."""
    try:
        with open(item_path) as f:
            content = f.read()

        new_line = f"{LANGSMITH_TRACE_LINE_PREFIX}{trace_id}"
        if LANGSMITH_TRACE_PATTERN.search(content):
            content = LANGSMITH_TRACE_PATTERN.sub(new_line, content)
        else:
            content = content.rstrip("\n") + f"\n\n{new_line}\n"

        with open(item_path, "w") as f:
            f.write(content)
    except OSError as exc:
        logger.debug("_write_trace_id_to_file failed (non-fatal): %s", exc)
