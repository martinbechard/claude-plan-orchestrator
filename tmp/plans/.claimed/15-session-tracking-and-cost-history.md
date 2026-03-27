# Session tracking with start time, cost history, and daily totals

## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


## Status: Open

## Priority: Medium

## Summary

The dashboard shows "Session Cost" but there is no concept of when a session
started, when it ended, or how to query historical sessions. A session is
currently just "time since the pipeline process started" which resets on
restart and has no persistence. We need proper session tracking to answer
questions like "how much did last night's run cost?" and "what is my daily
spend trend?"

## Requirements

### Session lifecycle
- A session starts when the pipeline starts (automatic) or when a human
  declares a new session via Slack command or dashboard button.
- A session can also start when the system detects capacity is getting low
  (quota warning) — this could mark the boundary of a billing period.
- A session ends when the pipeline stops, or when a new session is explicitly
  started.
- Each session has: start_time, end_time (null if active), total_cost_usd,
  items_processed, a human-readable label (optional).

### Persistence
- Store sessions in a new `sessions` table in the SQLite DB:
  id, label, start_time, end_time, total_cost_usd, items_processed.
- On pipeline startup, create a new session row. On shutdown, update end_time.
- All completion costs are attributed to the active session.

### Dashboard display
- Show session start time next to the session cost (e.g. "Session Cost:
  $4.23 (started 10:30 AM)").
- Add a "Session History" section or page showing past sessions with their
  date range, cost, and item count.

### Daily totals
- In addition to session-based tracking, compute daily cost totals from the
  completions table (GROUP BY date(finished_at)).
- Sessions and daily totals are complementary — a session may span midnight,
  and multiple sessions may occur in one day.
- Show both views: "Sessions" (by pipeline run) and "Daily" (by calendar
  day) in the cost history.

### Session boundaries from capacity events
- When the pipeline detects quota is getting low (existing quota probe), it
  could optionally mark the current session as "capacity warning" so the
  user can correlate cost with quota consumption.
- This is informational, not a hard boundary — the session continues.

## Implementation Notes

- New table: sessions (id, label, start_time, end_time, total_cost_usd,
  items_processed, notes)
- On pipeline startup in cli.py or supervisor.py: INSERT INTO sessions
- On shutdown: UPDATE sessions SET end_time = now WHERE end_time IS NULL
- DashboardState.snapshot() includes session_start_time (actual datetime,
  not just elapsed seconds)
- Daily totals: SELECT date(finished_at) as day, SUM(cost_usd) FROM
  completions GROUP BY day ORDER BY day DESC
- New endpoint: GET /sessions for session history page

## LangSmith Trace: 726158d5-528e-4d47-b12c-a3556b923355


## 5 Whys Analysis

I'll analyze this backlog item using the 5 Whys method:

---

**Title**: Establish persistent, time-bounded cost tracking for financial visibility

**Clarity**: 4/5
— The requirements are detailed and specific. The only minor ambiguity is the optional "capacity warning" correlation and edge cases where sessions span midnight.

**5 Whys**:

1. **Why do we need to track sessions with persistent start times and cost history?**
   → Because the current system resets cost tracking on every pipeline restart with no historical record, making it impossible to answer questions about costs over meaningful time periods.

2. **Why is running cost since the last restart insufficient?**
   → Because users need to understand cost patterns and trends over time (yesterday, this week) rather than just "since the process started" to make informed optimization and budget decisions.

3. **Why do we need both session-based AND daily cost views?**
   → Because sessions (pipeline runs) and calendar days are independent — a session may span midnight, multiple sessions may occur in one day, and users need to reconcile with both operational and billing periods.

4. **Why must costs be mapped to both operational and calendar-based time boundaries?**
   → Because users need to correlate cost spikes with specific events (which run was expensive, which calendar day had anomalies) to understand root causes and identify optimization opportunities.

5. **Why is detecting cost anomalies and optimizing spending critical?**
   → Because AI API usage costs are variable and unpredictable; without visibility, users cannot prevent budget overruns or detect when something went wrong (runaway processing, inefficient configuration, etc.).

---

**Root Need**: Budget control and anomaly visibility — users need persistent cost data grouped by both operational sessions and calendar days to prevent financial surprises and maintain spending oversight in variable-cost operations.

**Summary**: Users need persistent, time-bounded cost tracking (by session and calendar day) to detect anomalies and maintain proactive budget control.
