# Design: Periodic Progress Reporter

## Overview

Add a periodic progress reporter that runs inside the existing auto-pipeline
process (no separate daemon). Every N minutes (default 15), it sends a Slack
notification with pipeline throughput, ETA, and upcoming work. It stays silent
when the pipeline is idle.

## Architecture

### New class: ProgressReporter

A daemon thread similar to the existing CodeChangeMonitor pattern:

- Owns a threading.Event for clean shutdown
- Runs in a loop with _stop_event.wait(timeout=interval) as the sleep
- On each wake-up, gathers stats and sends a Slack message (or stays silent)

### Completion tracking: CompletionTracker

A lightweight in-memory tracker that records item completions:

- Uses a collections.deque of (timestamp, item_type, slug, duration_seconds) tuples
- process_item() and process_analysis_item() call tracker.record_completion()
  after a successful archive
- The deque retains entries for a configurable window (default: 2 hours)
  to compute velocity over a meaningful sample

### Report content

Each progress report includes:

1. Queue snapshot: count of items by type (defect/feature/analysis)
2. Completions in last interval: count + breakdown by type
3. Velocity: average completion time per item (from recent deque entries)
4. ETA: remaining queue size x average completion time (simple multiplication)
5. Next 5 queued items: name, type, priority (from scan_all_backlogs())

### Silence conditions

No report is sent if ALL of the following are true at wake-up time:

- No task is currently in progress (checked via a threading flag set/cleared by the main loop)
- No items are in any queue (scan_all_backlogs() returns empty)

### Configuration

- PROGRESS_REPORT_INTERVAL_SECONDS: constant, default 900 (15 minutes)
  Can be overridden via PIPELINE_REPORT_INTERVAL env var
- COMPLETION_HISTORY_WINDOW_SECONDS: constant, default 7200 (2 hours)

## Key files

| File | Change |
|------|--------|
| scripts/auto-pipeline.py | Add CompletionTracker class, ProgressReporter class, constants, integrate into main_loop() and process_item()/process_analysis_item() |
| tests/test_auto_pipeline.py | Unit tests for CompletionTracker, ProgressReporter silence logic, report formatting |

## Design decisions

1. In-memory tracking only: No persistence across restarts. The reporter uses
   a deque of recent completions. After a restart, the first interval may show
   zero velocity until items complete. This is simpler and avoids file I/O.

2. Simple ETA model: average_time_per_item x queue_size. No category-based
   adjustments in v1. The velocity naturally reflects the mix of work types
   being processed. This can be refined later if needed.

3. Daemon thread: Follows the CodeChangeMonitor pattern. The thread dies
   automatically with the main process.

4. No separate Slack channel: Reports go to the existing notifications channel
   (same as other pipeline status messages).

5. Thread-safe in-progress flag: A threading.Event (item_in_progress) is set
   before processing starts and cleared after processing ends. The reporter
   checks this flag for the silence condition.
