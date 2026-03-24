# Calculate tool call duration from timestamps instead of relying on reported duration

## Status: Open

## Priority: Medium

## Summary

Tool call durations are logged as 0.00 seconds in LangSmith despite correct start and end timestamps being recorded. The fix is to compute duration as `end_time - start_time` from the stored timestamps rather than relying on a separately reported duration field. This ensures timing data is always consistent and accurate by treating timestamps as the single source of truth.

## 5 Whys Analysis

  1. **Why are tool call durations showing as 0.00 seconds in LangSmith?** Because the duration value being logged is not computed from the actual start/end timestamps — it's either defaulting to zero or using an unreliable source value.
  2. **Why isn't the duration computed from the timestamps?** Because the logging code passes through a raw duration field (likely unset or zero) rather than calculating `end_time - start_time` from the timestamps that are already being captured correctly.
  3. **Why does the code rely on a raw duration field instead of calculating it?** Because the original implementation assumed the duration would be populated upstream or by the framework, rather than explicitly deriving it from the stored timestamps.
  4. **Why weren't the timestamps used as the source of truth from the start?** Because there was likely no validation step confirming that the reported duration matched the timestamp delta — the two data paths (timestamps vs. duration) were treated as independent rather than one being derived from the other.
  5. **Why is there no validation or single source of truth for timing data?** Because the instrumentation layer lacks a unified timing model where duration is always a computed property of timestamps, leading to inconsistencies when upstream sources provide incomplete data.

**Root Need:** Duration must be a computed value derived from start/end timestamps (the single source of truth), not an independently reported field that can default to zero.

## Source

Created from Slack message by U0AEWQYSLF9 at 1774329932.626699.
