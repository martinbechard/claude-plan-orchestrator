# langgraph_pipeline/shared/quota.py
# Quota exhaustion detection and probe utilities.
# Design: docs/plans/2026-03-24-01-detect-when-were-out-of-quota-in-claude-code-and-dont-process-any-further-ite-design.md

"""Quota exhaustion detection and availability probing for the pipeline.

Quota exhaustion is distinguished from rate limiting: rate limits carry a parseable
reset time; quota exhaustion does not (check_rate_limit returns (True, None)).
"""

from langgraph_pipeline.shared.claude_cli import call_claude
from langgraph_pipeline.shared.rate_limit import check_rate_limit

# ─── Constants ────────────────────────────────────────────────────────────────

QUOTA_PROBE_INTERVAL_SECONDS = 300  # 5-minute wait between availability probes
QUOTA_PROBE_PROMPT = "Reply with only the word OK"
QUOTA_PROBE_TIMEOUT_SECONDS = 30    # Timeout for a single probe call


# ─── Functions ────────────────────────────────────────────────────────────────


def detect_quota_exhaustion(output: str) -> bool:
    """Return True if output indicates quota exhaustion (not a parseable rate limit).

    Quota exhaustion is the case where check_rate_limit returns (True, None):
    the output signals a limit was hit but no reset time could be parsed.
    This distinguishes quota exhaustion from a normal rate limit with a known
    reset time.
    """
    is_limited, reset_time = check_rate_limit(output)
    return is_limited and reset_time is None


def probe_quota_available() -> bool:
    """Probe whether Claude is available by sending a minimal prompt.

    Returns True if Claude responds with a non-empty reply, False if the
    call fails or returns empty output (indicating quota still exhausted).
    """
    response = call_claude(QUOTA_PROBE_PROMPT, timeout=QUOTA_PROBE_TIMEOUT_SECONDS)
    return bool(response)
