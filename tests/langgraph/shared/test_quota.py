# tests/langgraph/shared/test_quota.py
# Unit tests for quota exhaustion detection and availability probing.
# Design: docs/plans/2026-03-24-02-detect-claude-code-quota-exhaustion-and-pause-pipeline-processing-design.md

"""Tests for langgraph_pipeline.shared.quota."""

from datetime import datetime, timezone
from unittest.mock import patch

from langgraph_pipeline.shared.quota import detect_quota_exhaustion, probe_quota_available


# ─── Tests: detect_quota_exhaustion ──────────────────────────────────────────


class TestDetectQuotaExhaustion:
    """detect_quota_exhaustion distinguishes quota exhaustion from parseable rate limits."""

    def test_rate_limited_with_reset_time_returns_false(self):
        """A parseable reset time means normal rate limiting, not quota exhaustion."""
        reset = datetime(2026, 3, 25, 6, 0, tzinfo=timezone.utc)
        with patch(
            "langgraph_pipeline.shared.quota.check_rate_limit",
            return_value=(True, reset),
        ):
            assert detect_quota_exhaustion("some output") is False

    def test_rate_limited_without_reset_time_returns_true(self):
        """No reset time means quota exhaustion — Claude cannot parse a recovery window."""
        with patch(
            "langgraph_pipeline.shared.quota.check_rate_limit",
            return_value=(True, None),
        ):
            assert detect_quota_exhaustion("some output") is True

    def test_no_rate_limit_returns_false(self):
        """Normal output with no rate-limit signal is not quota exhaustion."""
        with patch(
            "langgraph_pipeline.shared.quota.check_rate_limit",
            return_value=(False, None),
        ):
            assert detect_quota_exhaustion("normal output") is False


# ─── Tests: probe_quota_available ────────────────────────────────────────────


class TestProbeQuotaAvailable:
    """probe_quota_available returns True when Claude gives a non-empty response."""

    def test_non_empty_response_returns_true(self):
        """A non-empty reply from Claude means quota has been restored."""
        with patch(
            "langgraph_pipeline.shared.quota.call_claude",
            return_value="OK",
        ):
            assert probe_quota_available() is True

    def test_empty_response_returns_false(self):
        """An empty reply means Claude is still unavailable (quota still exhausted)."""
        with patch(
            "langgraph_pipeline.shared.quota.call_claude",
            return_value="",
        ):
            assert probe_quota_available() is False
