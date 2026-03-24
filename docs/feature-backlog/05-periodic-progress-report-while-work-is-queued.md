# Periodic progress report while work is in progress or queued

## Status: Open

## Priority: Medium

## Summary

The old `scripts/auto-pipeline.py` sent a periodic Slack progress report while backlog
items were active or queued. This was not carried over to the LangGraph rewrite. The
report fired every 15 minutes (PROGRESS_REPORT_INTERVAL_SECONDS = 900, overridable via
PIPELINE_REPORT_INTERVAL env var), was suppressed entirely when the pipeline was idle
(nothing running and all backlogs empty), and included: queue depth by type, average
item completion time (rolling 2-hour window), estimated time to clear the queue, and
the name of the next item up.

The feature was built from two classes:

- `CompletionTracker` — records (timestamp, type, slug, duration_s) for each completed
  item, prunes entries older than COMPLETION_HISTORY_WINDOW_SECONDS (7200 s), and
  exposes `completions_since(t)` and `average_duration_seconds()`.
- `ProgressReporter` — background thread that wakes every PROGRESS_REPORT_INTERVAL_SECONDS,
  calls `_should_report()` (True if item_in_progress event is set OR backlogs are
  non-empty), builds a report string via `_build_report(queue)`, and posts it to Slack.

The report format included sections: Queue (count by type), Avg completion time, ETA
(queue depth × avg duration), and Next up (slug of the first queued item).

## 5 Whys Analysis

1. **Why does the pipeline no longer send progress reports?** Because `ProgressReporter`
   and `CompletionTracker` existed only in `auto-pipeline.py` and were not migrated to
   the LangGraph rewrite.
2. **Why does that matter?** During long overnight runs, there is no signal that the
   pipeline is alive and making progress unless you watch logs — the only Slack messages
   are per-item completions and errors.
3. **Why isn't per-item notification enough?** A slow or stalled queue produces silence;
   without a heartbeat-style report, it is impossible to distinguish "working steadily"
   from "stuck" during an unattended run.
4. **Why was it suppressed when idle?** To avoid noise — if there is nothing to do, the
   pipeline should be silent; the report is only meaningful when there is work to track.
5. **Why is an average-based ETA useful?** It gives the operator a rough sense of when
   the queue will drain without requiring exact per-task estimates, using only observed
   historical durations from the rolling window.

**Root Need:** Restore the periodic heartbeat/progress report in the LangGraph pipeline
so operators can tell at a glance that unattended runs are alive, how much work remains,
and roughly when it will finish.

## Implementation Notes

- Reference implementation: `CompletionTracker`, `ProgressReporter`,
  `PROGRESS_REPORT_INTERVAL_SECONDS`, `COMPLETION_HISTORY_WINDOW_SECONDS` in
  `scripts/auto-pipeline.py`. Test coverage in `tests/test_auto_pipeline.py` lines
  1160-1282 documents the exact expected behaviour.
- The `CompletionTracker` should live in a shared module (e.g.
  `langgraph_pipeline/shared/progress.py`) so both the pipeline graph and any future
  executor extensions can record completions.
- The LangGraph pipeline's `scan_backlog` node (or the main CLI loop) is the right place
  to check the `restart_pending`-style event and trigger the report.
- The `item_in_progress` signal maps to the pipeline graph being actively executing a
  plan (i.e., not in the idle scan/sleep cycle).
- Post to the existing `orchestrator-notifications` Slack channel via `SlackNotifier`.
- PROGRESS_REPORT_INTERVAL_SECONDS should remain overridable via a
  `PIPELINE_REPORT_INTERVAL` environment variable for testing.

## Source

Identified as a regression from the LangGraph rewrite; original feature reverse-engineered
from tests in `tests/test_auto_pipeline.py`.
