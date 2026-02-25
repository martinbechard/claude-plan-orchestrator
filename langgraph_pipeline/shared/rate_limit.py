# langgraph_pipeline/shared/rate_limit.py
# Rate limit detection and wait helpers shared by auto-pipeline.py and plan-orchestrator.py.
# Design: docs/plans/2026-02-25-02-extract-shared-modules-design.md

"""Rate limit parsing, detection, and wait utilities for the Claude CLI."""

import re
import time
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

# ─── Constants ────────────────────────────────────────────────────────────────

RATE_LIMIT_DEFAULT_WAIT_SECONDS = 3600  # 1-hour fallback when reset time is unparseable
RATE_LIMIT_BUFFER_SECONDS = 30          # Extra padding added after the stated reset time

RATE_LIMIT_PATTERN = re.compile(
    r"(?:You've hit your limit|you've hit your limit|Usage limit reached)"
    r".*?resets?\s+(\w+\s+\d{1,2})\s+at\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM)?)"
    r"(?:\s*\(([^)]+)\))?",
    re.IGNORECASE | re.DOTALL,
)

MONTH_NAMES = {
    "jan": 1, "january": 1, "feb": 2, "february": 2,
    "mar": 3, "march": 3, "apr": 4, "april": 4,
    "may": 5, "jun": 6, "june": 6,
    "jul": 7, "july": 7, "aug": 8, "august": 8,
    "sep": 9, "september": 9, "oct": 10, "october": 10,
    "nov": 11, "november": 11, "dec": 12, "december": 12,
}


# ─── Functions ────────────────────────────────────────────────────────────────

def parse_rate_limit_reset_time(output: str) -> Optional[datetime]:
    """Parse a rate limit reset time from Claude CLI output.

    Recognizes messages like:
      "You've hit your limit · resets Feb 9 at 6pm (America/Toronto)"
      "You've hit your limit · resets February 9 at 6:30pm (America/Toronto)"
      "You've hit your limit · resets Feb 9 at 18:00 (America/Toronto)"

    Returns a timezone-aware datetime if parseable, None otherwise.
    """
    match = RATE_LIMIT_PATTERN.search(output)
    if not match:
        return None

    date_str = match.group(1).strip()   # e.g. "Feb 9"
    time_str = match.group(2).strip()   # e.g. "6pm", "6:30pm", or "18:00"
    tz_str = match.group(3)             # e.g. "America/Toronto" or None

    try:
        parts = date_str.split()
        month_name = parts[0].lower()
        day = int(parts[1])
        month = MONTH_NAMES.get(month_name)
        if month is None:
            print(f"[RATE LIMIT] Could not parse month: {month_name}")
            return None

        # Parse time - handles "6pm", "6:30pm", "18:00", "6"
        time_str_lower = time_str.lower().strip()
        hour = 0
        minute = 0

        if "am" in time_str_lower or "pm" in time_str_lower:
            is_pm = "pm" in time_str_lower
            time_digits = time_str_lower.replace("am", "").replace("pm", "").strip()
            if ":" in time_digits:
                hour_str, min_str = time_digits.split(":")
                hour = int(hour_str)
                minute = int(min_str)
            else:
                hour = int(time_digits)
            if is_pm and hour != 12:
                hour += 12
            elif not is_pm and hour == 12:
                hour = 0
        elif ":" in time_str_lower:
            hour_str, min_str = time_str_lower.split(":")
            hour = int(hour_str)
            minute = int(min_str)
        else:
            hour = int(time_str_lower)

        tz = ZoneInfo("UTC")
        if tz_str:
            try:
                tz = ZoneInfo(tz_str.strip())
            except (KeyError, ValueError):
                print(f"[RATE LIMIT] Unknown timezone '{tz_str}', using UTC")

        now = datetime.now(tz)
        reset_time = now.replace(month=month, day=day, hour=hour, minute=minute, second=0, microsecond=0)

        # If the computed reset time is in the past, assume it wraps to next year
        if reset_time < now - timedelta(hours=1):
            reset_time = reset_time.replace(year=now.year + 1)

        return reset_time

    except (ValueError, IndexError) as e:
        print(f"[RATE LIMIT] Failed to parse reset time: {e}")
        return None


def check_rate_limit(output: str) -> tuple[bool, Optional[datetime]]:
    """Check if output contains a rate limit message.

    Returns (is_rate_limited, reset_time).
    reset_time is None when rate limited but the reset time could not be parsed.
    """
    if not re.search(r"(?:You've hit your limit|Usage limit reached)", output, re.IGNORECASE):
        return False, None

    reset_time = parse_rate_limit_reset_time(output)
    return True, reset_time


def wait_for_rate_limit_reset(reset_time: Optional[datetime]) -> bool:
    """Sleep until the rate limit resets.

    If reset_time is None, sleeps for RATE_LIMIT_DEFAULT_WAIT_SECONDS.
    Returns True if the wait completed, False if interrupted by the user.
    """
    if reset_time:
        now = datetime.now(reset_time.tzinfo)
        wait_seconds = (reset_time - now).total_seconds()
        if wait_seconds <= 0:
            print("[RATE LIMIT] Reset time already passed, continuing immediately")
            return True
        wait_seconds += RATE_LIMIT_BUFFER_SECONDS
        reset_str = reset_time.strftime("%Y-%m-%d %H:%M %Z")
        print(f"\n[RATE LIMIT] API rate limit hit. Resets at: {reset_str}")
        print(f"[RATE LIMIT] Sleeping for {wait_seconds:.0f}s ({wait_seconds / 60:.1f} minutes)")
    else:
        wait_seconds = RATE_LIMIT_DEFAULT_WAIT_SECONDS
        print(f"\n[RATE LIMIT] API rate limit hit. Could not parse reset time.")
        print(f"[RATE LIMIT] Sleeping for default {wait_seconds}s ({wait_seconds / 60:.0f} minutes)")

    print("[RATE LIMIT] Press Ctrl+C to abort")
    try:
        time.sleep(wait_seconds)
        print("[RATE LIMIT] Wait complete, resuming...")
        return True
    except KeyboardInterrupt:
        print("\n[RATE LIMIT] Aborted by user")
        return False
