# tests/langgraph/shared/test_rate_limit.py
# Unit tests for the shared rate_limit module.
# Design: docs/plans/2026-02-25-02-extract-shared-modules-design.md

"""Unit tests for langgraph_pipeline.shared.rate_limit."""

import re
from datetime import datetime, timedelta
from typing import Optional
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from langgraph_pipeline.shared.rate_limit import (
    MONTH_NAMES,
    RATE_LIMIT_BUFFER_SECONDS,
    RATE_LIMIT_DEFAULT_WAIT_SECONDS,
    RATE_LIMIT_PATTERN,
    check_rate_limit,
    parse_rate_limit_reset_time,
    wait_for_rate_limit_reset,
)


class TestConstants:
    def test_default_wait_is_one_hour(self):
        assert RATE_LIMIT_DEFAULT_WAIT_SECONDS == 3600

    def test_buffer_seconds_is_positive(self):
        assert RATE_LIMIT_BUFFER_SECONDS > 0

    def test_month_names_has_12_months(self):
        unique_months = set(MONTH_NAMES.values())
        assert unique_months == set(range(1, 13))

    def test_month_names_accepts_abbreviations(self):
        for abbrev in ["jan", "feb", "mar", "apr", "may", "jun",
                       "jul", "aug", "sep", "oct", "nov", "dec"]:
            assert abbrev in MONTH_NAMES

    def test_month_names_accepts_full_names(self):
        for full in ["january", "february", "march", "april", "june",
                     "july", "august", "september", "october", "november", "december"]:
            assert full in MONTH_NAMES

    def test_rate_limit_pattern_is_compiled_regex(self):
        assert hasattr(RATE_LIMIT_PATTERN, "search")


class TestParseRateLimitResetTime:
    """Tests for parse_rate_limit_reset_time()."""

    def _fake_now(self, tz: ZoneInfo) -> datetime:
        return datetime(2026, 1, 1, 12, 0, 0, tzinfo=tz)

    def test_returns_none_for_unrelated_output(self):
        assert parse_rate_limit_reset_time("Everything is fine.") is None

    def test_returns_none_for_empty_string(self):
        assert parse_rate_limit_reset_time("") is None

    def test_parses_short_month_pm_format(self):
        output = "You've hit your limit · resets Feb 9 at 6pm (America/Toronto)"
        tz = ZoneInfo("America/Toronto")
        fake_now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=tz)
        with patch("langgraph_pipeline.shared.rate_limit.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
            result = parse_rate_limit_reset_time(output)
        assert result is not None
        assert result.month == 2
        assert result.day == 9
        assert result.hour == 18
        assert result.minute == 0

    def test_parses_full_month_with_minutes(self):
        output = "You've hit your limit · resets February 9 at 6:30pm (America/Toronto)"
        tz = ZoneInfo("America/Toronto")
        fake_now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=tz)
        with patch("langgraph_pipeline.shared.rate_limit.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
            result = parse_rate_limit_reset_time(output)
        assert result is not None
        assert result.month == 2
        assert result.day == 9
        assert result.hour == 18
        assert result.minute == 30

    def test_parses_24h_time_format(self):
        output = "You've hit your limit · resets Mar 15 at 18:00 (UTC)"
        tz = ZoneInfo("UTC")
        fake_now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=tz)
        with patch("langgraph_pipeline.shared.rate_limit.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
            result = parse_rate_limit_reset_time(output)
        assert result is not None
        assert result.hour == 18
        assert result.minute == 0

    def test_parses_usage_limit_reached_message(self):
        output = "Usage limit reached · resets Apr 1 at 10am (UTC)"
        tz = ZoneInfo("UTC")
        fake_now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=tz)
        with patch("langgraph_pipeline.shared.rate_limit.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
            result = parse_rate_limit_reset_time(output)
        assert result is not None
        assert result.month == 4
        assert result.hour == 10

    def test_midnight_am_conversion(self):
        """12am should map to hour 0."""
        output = "You've hit your limit · resets Jun 1 at 12am (UTC)"
        tz = ZoneInfo("UTC")
        fake_now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=tz)
        with patch("langgraph_pipeline.shared.rate_limit.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
            result = parse_rate_limit_reset_time(output)
        assert result is not None
        assert result.hour == 0

    def test_noon_pm_stays_12(self):
        """12pm should remain hour 12."""
        output = "You've hit your limit · resets Jun 1 at 12pm (UTC)"
        tz = ZoneInfo("UTC")
        fake_now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=tz)
        with patch("langgraph_pipeline.shared.rate_limit.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
            result = parse_rate_limit_reset_time(output)
        assert result is not None
        assert result.hour == 12

    def test_falls_back_to_utc_for_unknown_timezone(self, capsys):
        output = "You've hit your limit · resets Dec 31 at 11pm (Invalid/Zone)"
        tz = ZoneInfo("UTC")
        fake_now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=tz)
        with patch("langgraph_pipeline.shared.rate_limit.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
            result = parse_rate_limit_reset_time(output)
        captured = capsys.readouterr()
        assert "Unknown timezone" in captured.out
        assert result is not None

    def test_returns_none_for_no_timezone(self):
        """Without a timezone group the function still parses (no-tz group → UTC)."""
        output = "You've hit your limit · resets May 5 at 9am"
        tz = ZoneInfo("UTC")
        fake_now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=tz)
        with patch("langgraph_pipeline.shared.rate_limit.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
            result = parse_rate_limit_reset_time(output)
        assert result is not None
        assert result.hour == 9


class TestCheckRateLimit:
    """Tests for check_rate_limit()."""

    def test_returns_false_none_for_normal_output(self):
        is_limited, reset_time = check_rate_limit("Task completed successfully.")
        assert is_limited is False
        assert reset_time is None

    def test_returns_true_for_hit_your_limit(self):
        output = "You've hit your limit · resets Feb 9 at 6pm (UTC)"
        tz = ZoneInfo("UTC")
        fake_now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=tz)
        with patch("langgraph_pipeline.shared.rate_limit.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
            is_limited, reset_time = check_rate_limit(output)
        assert is_limited is True
        assert reset_time is not None

    def test_returns_true_for_usage_limit_reached(self):
        output = "Usage limit reached · resets Mar 1 at 8am (UTC)"
        tz = ZoneInfo("UTC")
        fake_now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=tz)
        with patch("langgraph_pipeline.shared.rate_limit.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
            is_limited, reset_time = check_rate_limit(output)
        assert is_limited is True

    def test_returns_true_with_none_reset_time_when_unparseable(self):
        output = "You've hit your limit - no time info here"
        is_limited, reset_time = check_rate_limit(output)
        assert is_limited is True
        assert reset_time is None

    def test_return_type_is_tuple(self):
        result = check_rate_limit("normal output")
        assert isinstance(result, tuple)
        assert len(result) == 2


class TestWaitForRateLimitReset:
    """Tests for wait_for_rate_limit_reset()."""

    def test_returns_true_when_reset_time_already_passed(self, capsys):
        tz = ZoneInfo("UTC")
        past_time = datetime(2025, 1, 1, 0, 0, 0, tzinfo=tz)
        with patch("langgraph_pipeline.shared.rate_limit.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 6, 1, 12, 0, 0, tzinfo=tz)
        result = wait_for_rate_limit_reset(past_time)
        assert result is True
        captured = capsys.readouterr()
        assert "already passed" in captured.out

    def test_returns_true_after_sleep_completes(self, capsys):
        tz = ZoneInfo("UTC")
        future_time = datetime(2026, 12, 31, 23, 59, 0, tzinfo=tz)
        now = datetime(2026, 12, 31, 23, 58, 0, tzinfo=tz)
        with patch("langgraph_pipeline.shared.rate_limit.datetime") as mock_dt:
            mock_dt.now.return_value = now
            with patch("langgraph_pipeline.shared.rate_limit.time.sleep") as mock_sleep:
                result = wait_for_rate_limit_reset(future_time)
        assert result is True
        mock_sleep.assert_called_once()

    def test_returns_false_on_keyboard_interrupt(self, capsys):
        tz = ZoneInfo("UTC")
        future_time = datetime(2026, 12, 31, 23, 59, 0, tzinfo=tz)
        now = datetime(2026, 12, 31, 23, 58, 0, tzinfo=tz)
        with patch("langgraph_pipeline.shared.rate_limit.datetime") as mock_dt:
            mock_dt.now.return_value = now
            with patch("langgraph_pipeline.shared.rate_limit.time.sleep",
                       side_effect=KeyboardInterrupt):
                result = wait_for_rate_limit_reset(future_time)
        assert result is False
        captured = capsys.readouterr()
        assert "Aborted" in captured.out

    def test_sleeps_default_when_reset_time_is_none(self):
        with patch("langgraph_pipeline.shared.rate_limit.time.sleep") as mock_sleep:
            result = wait_for_rate_limit_reset(None)
        assert result is True
        mock_sleep.assert_called_once_with(RATE_LIMIT_DEFAULT_WAIT_SECONDS)

    def test_sleep_includes_buffer_when_reset_time_provided(self):
        tz = ZoneInfo("UTC")
        now = datetime(2026, 6, 1, 12, 0, 0, tzinfo=tz)
        future_time = datetime(2026, 6, 1, 12, 1, 0, tzinfo=tz)  # 60s in the future
        with patch("langgraph_pipeline.shared.rate_limit.datetime") as mock_dt:
            mock_dt.now.return_value = now
            with patch("langgraph_pipeline.shared.rate_limit.time.sleep") as mock_sleep:
                wait_for_rate_limit_reset(future_time)
        called_seconds = mock_sleep.call_args[0][0]
        assert called_seconds == pytest.approx(60 + RATE_LIMIT_BUFFER_SECONDS, abs=1)
