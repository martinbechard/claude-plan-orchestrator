# langgraph_pipeline/executor/circuit_breaker.py
# Circuit breaker for the task execution subgraph.
# Design: docs/plans/2026-02-26-05-task-execution-subgraph-design.md

"""Circuit breaker logic for the executor subgraph.

Tracks consecutive task failures and stops execution when the threshold is
exceeded.  The counter resets to zero on any successful task completion.
"""

# ─── Constants ────────────────────────────────────────────────────────────────

DEFAULT_FAILURE_THRESHOLD = 3


# ─── Public API ───────────────────────────────────────────────────────────────


def is_circuit_open(consecutive_failures: int, threshold: int = DEFAULT_FAILURE_THRESHOLD) -> bool:
    """Return True when consecutive failures have reached or exceeded the threshold.

    Args:
        consecutive_failures: Current count of back-to-back task failures.
        threshold: Maximum allowed failures before the circuit opens.

    Returns:
        True if execution should halt; False if execution may continue.
    """
    return consecutive_failures >= threshold


def record_failure(consecutive_failures: int) -> int:
    """Increment the consecutive failure counter after a task fails.

    Args:
        consecutive_failures: Current counter value.

    Returns:
        Incremented counter value.
    """
    return consecutive_failures + 1


def reset_failures() -> int:
    """Reset the consecutive failure counter after a task succeeds.

    Returns:
        Zero, representing a clean slate.
    """
    return 0
