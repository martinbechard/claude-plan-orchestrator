# Periodic Progress Reporter

## Status: Open

## Priority: Medium

## Summary

Add a periodic progress reporter that wakes up on a configurable interval (default 15
minutes) and sends a Slack notification to the project notifications channel with pipeline
throughput statistics, estimated completion time, and a preview of upcoming work items.

The reporter must be silent when the pipeline is idle -- if no task is currently in progress
and no items are queued, no notification is sent. This avoids noise when a single item is
submitted and completes quickly before the next wake-up.

## Requirements

### Notification content

Each progress report should include:

- Number of items currently queued (broken down by type: defects, features, analyses)
- Number of items completed in the last reporting interval
- Velocity: average completion time per item over the last interval
- Estimated time to complete remaining queued items (based on recent velocity, with
  reasonable complexity adjustments left to the design phase -- keep it simple)
- A preview of the next 5 queued items (name, type, priority)

### Silence conditions

Do NOT send a report if ALL of the following are true at wake-up time:

- No task is currently in progress
- No items are in any queue (defect, feature, analysis)

### Configuration

- The reporting interval should be configurable (constant or env var), defaulting to
  15 minutes
- Reporting runs inside the existing auto-pipeline process (no separate daemon)

### Slack integration

- Send reports to the project-specific notifications channel (same channel used by
  existing pipeline status messages)
- Use the existing SlackNotifier infrastructure

### Complexity estimation

- The design phase should determine the right level of sophistication for ETA estimates
- Start simple (e.g. average of recent completions), and avoid over-engineering
- Category-based adjustments (defects vs features) are acceptable if they emerge
  naturally from the data

## Files Affected

| File | Change |
|------|--------|
| scripts/auto-pipeline.py | Add periodic reporter thread/timer, tracking of completion timestamps, report generation logic |
| scripts/plan-orchestrator.py | Possibly expose per-item timing data for the reporter to consume |

## Dependencies

None

## Verification Log

### Task 1.1 - FAIL (2026-02-19 16:02)
  - Validator 'validator' failed to execute: No status file written by Claude

### Task 1.1 - FAIL (2026-02-19 16:05)
  - Validator 'validator' failed to execute: No status file written by Claude

### Task 2.1 - FAIL (2026-02-19 16:10)
  - Validator 'validator' failed to execute: No status file written by Claude

### Task 3.1 - FAIL (2026-02-19 16:20)
  - Validator 'validator' failed to execute: No status file written by Claude

### Task 3.1 - FAIL (2026-02-19 16:24)
  - Validator 'validator' failed to execute: No status file written by Claude

### Task 4.1 - FAIL (2026-02-19 16:29)
  - Validator 'validator' failed to execute: No status file written by Claude

### Task 4.1 - FAIL (2026-02-19 16:32)
  - Validator 'validator' failed to execute: No status file written by Claude
