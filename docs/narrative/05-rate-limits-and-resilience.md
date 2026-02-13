# Chapter 5: Rate Limits and Resilience

**Commit:** `1da6427` --- 2026-02-09
**Size:** ~150 new lines
**Title:** "feat: add rate limit detection and auto-retry to orchestrator"

## The Problem

When running multi-hour plans with dozens of tasks, hitting Anthropic's API rate limits
was inevitable. Before this commit, a rate-limited task would:

1. Fail with a non-zero exit code
2. Be counted as a regular failure (incrementing the attempt counter)
3. Trigger exponential backoff via the circuit breaker
4. Eventually exhaust all retries and be marked as "failed"

This was wasteful. A rate limit isn't a real failure --- it's a temporary condition that
resolves on its own. Burning retry attempts on rate limits meant genuine failures had
fewer chances to recover.

## The Solution: Parse the Rate Limit Message

Claude CLI outputs a human-readable message when rate-limited:

```
You've hit your limit - resets Feb 9 at 6pm (America/Toronto)
```

The orchestrator now parses this message with a regex:

```python
RATE_LIMIT_PATTERN = re.compile(
    r"(?:You've hit your limit|you've hit your limit|Usage limit reached)"
    r".*?resets?\s+(\w+\s+\d{1,2})\s+at\s+"
    r"(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM)?)"
    r"(?:\s*\(([^)]+)\))?",
    re.IGNORECASE | re.DOTALL,
)
```

This captures three groups:
1. The date: `Feb 9`
2. The time: `6pm` or `6:30pm`
3. The timezone: `America/Toronto` (optional)

## Timezone-Aware Wait Logic

The parsed reset time is converted to a proper timezone-aware datetime:

```python
def parse_rate_limit_reset_time(output):
    match = RATE_LIMIT_PATTERN.search(output)
    date_str = match.group(1)  # "Feb 9"
    time_str = match.group(2)  # "6pm"
    tz_str = match.group(3)    # "America/Toronto"

    # Parse month, day, hour, minute
    month = MONTH_NAMES.get(month_name)
    # Handle "6pm", "6:30pm", "18:00" formats
    if "pm" in time_str_lower:
        is_pm = True
        ...

    # Build timezone-aware datetime
    tz = ZoneInfo(tz_str.strip()) if tz_str else ZoneInfo("UTC")
    reset_time = now.replace(month=month, day=day, hour=hour, minute=minute)

    # Handle year rollover (rate limit in January, currently December)
    if reset_time < now - timedelta(hours=1):
        reset_time = reset_time.replace(year=now.year + 1)

    return reset_time
```

The use of `zoneinfo.ZoneInfo` (Python 3.9+) for proper IANA timezone handling is
notable --- it correctly handles DST transitions and the fact that Claude's rate limit
messages use the user's local timezone.

## The Wait Strategy

When a rate limit is detected, the orchestrator sleeps until the reset time plus a
30-second buffer:

```python
def wait_for_rate_limit_reset(reset_time):
    if reset_time:
        wait_seconds = (reset_time - now).total_seconds() + 30  # 30s buffer
        print(f"[RATE LIMIT] Sleeping for {wait_seconds:.0f}s ({wait_seconds/60:.1f} min)")
    else:
        wait_seconds = 3600  # 1 hour fallback
        print(f"[RATE LIMIT] Could not parse reset time. Sleeping 1 hour.")

    print("[RATE LIMIT] Press Ctrl+C to abort")
    try:
        time.sleep(wait_seconds)
        return True
    except KeyboardInterrupt:
        print("[RATE LIMIT] Aborted by user")
        return False
```

Key design decisions:
- **30-second buffer** prevents edge cases where the clock is slightly off
- **1-hour fallback** when parsing fails (conservative but safe)
- **Ctrl+C escape** lets the human abort if the wait is unreasonable
- **Rate limits don't count as failures** --- attempt counter is decremented:

```python
if task_result.rate_limited:
    # Don't count rate limits as circuit breaker failures
    # Don't increment attempt count - this wasn't a real failure
    task["attempts"] = max(0, task.get("attempts", 1) - 1)
```

## Rate Limits in Parallel Mode

The same logic applies to parallel tasks, but with a twist: when *any* task in a
parallel group hits a rate limit, the entire group is reset:

```python
rate_limited_results = [r for r in results.values() if r and r.rate_limited]
if rate_limited_results:
    # Find the latest reset time among all rate-limited tasks
    reset_times = [r.rate_limit_reset_time for r in rate_limited_results
                   if r.rate_limit_reset_time]
    latest_reset = max(reset_times) if reset_times else None

    # Reset all tasks in the group to pending
    for section, task, _ in parallel_tasks:
        task["status"] = "pending"
        task["attempts"] = max(0, task.get("attempts", 1) - 1)

    # Wait for the latest reset time
    should_continue = wait_for_rate_limit_reset(latest_reset)
    if should_continue:
        continue  # Retry the entire parallel group
```

This is the correct behavior: if 3 parallel tasks run and 1 hits a rate limit, the
other 2 may have succeeded. But the rate limit means we can't run the failed task
immediately, and we might hit the limit again if we try the other pending tasks.
The safest approach is to wait for the longest reset time and retry everything.

## The TaskResult Extension

The `TaskResult` dataclass was extended with rate limit fields:

```python
@dataclass
class TaskResult:
    success: bool
    message: str
    duration_seconds: float
    plan_modified: bool = False
    rate_limited: bool = False                    # NEW
    rate_limit_reset_time: Optional[datetime] = None  # NEW
```

This keeps rate limit information flowing through the entire result pipeline without
breaking existing code that only checks `success`.

## Questions

**Q: Why parse the human-readable message instead of checking HTTP status codes?**
The orchestrator doesn't have direct access to the API --- it spawns `claude` CLI as
a subprocess. The CLI's exit code doesn't distinguish between rate limits and other
failures. The human-readable message in stderr/stdout is the only signal available.
This is fragile (the message format could change), but it's the best option given
the architecture.

**Q: What happens if Anthropic changes the rate limit message format?**
The regex would fail to match, `parse_rate_limit_reset_time` would return `None`,
and the orchestrator would fall back to the 1-hour default wait. Not ideal but not
catastrophic. The `RATE_LIMIT_PATTERN` is a single constant that's easy to update.

**Q: Could the orchestrator pre-calculate when it will hit rate limits?**
In theory, yes --- by tracking API usage per session and comparing against known limits.
In practice, the limits are complex (per-model, per-tier, sliding windows) and the
orchestrator doesn't have visibility into the Claude CLI's actual API usage. Reactive
detection is simpler and more reliable than predictive avoidance.
