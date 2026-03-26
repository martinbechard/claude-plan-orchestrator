# langgraph_pipeline/shared/shutdown.py
# Shared shutdown event singleton for cross-module signal coordination.
# Design: docs/plans/2026-03-26-21-intake-throttle-warns-but-doesnt-block-design.md

"""Shared shutdown event singleton.

Provides a single threading.Event that both the CLI signal handlers and
pipeline nodes (e.g. intake throttle wait loop) can access without passing
the event through the LangGraph state (which cannot hold non-serialisable objects).
"""

import threading

# ─── Module-level singleton ───────────────────────────────────────────────────

_shutdown_event: threading.Event = threading.Event()


# ─── Public API ───────────────────────────────────────────────────────────────


def get_shutdown_event() -> threading.Event:
    """Return the shared shutdown event.

    If register_shutdown_event() has not been called (e.g. in tests), returns
    the default module-level event so callers work without explicit wiring.

    Returns:
        The shared threading.Event used to signal clean shutdown.
    """
    return _shutdown_event


def register_shutdown_event(event: threading.Event) -> None:
    """Replace the default singleton with the event created by cli.py.

    Call this immediately after creating the shutdown event in main() so that
    signal handlers and pipeline nodes share the same object.

    Args:
        event: The threading.Event created by cli.main() and passed to signal handlers.
    """
    global _shutdown_event
    _shutdown_event = event
