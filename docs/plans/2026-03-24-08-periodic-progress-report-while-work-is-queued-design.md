# Design: Periodic Progress Report While Work Is Queued

**Feature:** 08-periodic-progress-report-while-work-is-queued
**Date:** 2026-03-24
**Source:** docs/feature-backlog/08-periodic-progress-report-while-work-is-queued.md

## Overview

Restore the periodic Slack progress heartbeat in the LangGraph pipeline. When the
backlog has queued items or an item is actively being processed, the pipeline posts
a report every 15 minutes (configurable via `PIPELINE_REPORT_INTERVAL`) showing
queue depth by type, rolling average completion time, estimated time to drain, and
the next item up. The report is suppressed entirely when the pipeline is idle.

This mirrors the `CompletionTracker` + `ProgressReporter` pattern from
`scripts/auto-pipeline.py` (see plan 18), adapted for the LangGraph CLI loop in
`langgraph_pipeline/cli.py`.

## Architecture

### New file: `langgraph_pipeline/shared/progress.py`

Houses two classes and their constants:

**`CompletionTracker`** — thread-safe rolling history of completed items.

- Backed by a `collections.deque`; each entry is `(timestamp, item_type, slug, duration_s)`.
- `record_completion(item_type, slug, duration_s)` — appends and prunes stale entries.
- `average_duration_seconds()` — mean duration over the `COMPLETION_HISTORY_WINDOW_SECONDS`
  window (0.0 when empty).
- `completions_since(since_timestamp)` — list of entries newer than the given time.
- Thread-safe via `threading.Lock`.

**`ProgressReporter(threading.Thread)`** — daemon thread following the `CodeChangeMonitor`
pattern from `langgraph_pipeline/shared/hot_reload.py`.

- Wakes every `PROGRESS_REPORT_INTERVAL_SECONDS` using `_stop_event.wait(timeout=...)`.
- `_should_report()` returns `True` if:
  - `item_in_progress` event is set (graph actively executing), OR
  - any backlog directory contains ready items.
- `_build_report(queue_items)` assembles a Slack message with:
  - Queue count by type (defect / feature / analysis).
  - Completions since the last report.
  - Average completion time (rolling window).
  - ETA (queue_depth × average_time).
  - Name of the next queued item.
- Posts to the existing `orchestrator-notifications` channel via `SlackNotifier.send_status()`.
- `start()` / `stop()` follow the `CodeChangeMonitor` interface.

Constants (module-level, overridable via env):

```
PROGRESS_REPORT_INTERVAL_SECONDS = int(os.environ.get("PIPELINE_REPORT_INTERVAL", "900"))
COMPLETION_HISTORY_WINDOW_SECONDS = 7200
```

### Modified: `langgraph_pipeline/cli.py`

Changes confined to `_run_scan_loop()` (sequential path only; supervisor loop is out
of scope):

1. Create `item_in_progress = threading.Event()`.
2. Create `completion_tracker = CompletionTracker()`.
3. Create and start `reporter = ProgressReporter(slack, completion_tracker, item_in_progress)`.
4. Before each `graph.invoke()`, record `start_time = time.monotonic()` and set
   `item_in_progress`.
5. After `graph.invoke()` returns (success or quota-exhausted), clear `item_in_progress`
   and call `completion_tracker.record_completion(item_type, slug, elapsed)`.
6. Stop `reporter` in the `finally` block alongside `code_monitor.stop()`.

No changes to `PipelineState`, graph nodes, or `archival.py` — the CLI loop has all
information required to record completions.

### New file: `tests/test_progress.py`

Unit tests for both classes following the pattern in `tests/test_hot_reload.py`:

- `CompletionTracker`: record/retrieve, prune-old, average-duration, empty state, constants.
- `ProgressReporter`: silent-when-idle, reports-when-active, reports-when-queued, report-format.

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Record completions in CLI loop, not in `archive` node | CLI already has start time, slug, type; avoids threading shared state through PipelineState |
| Separate `progress.py` shared module | Mirrors `hot_reload.py` pattern; keeps pipeline nodes free of background-thread logic |
| `_stop_event.wait(timeout=...)` instead of `time.sleep()` | Allows clean shutdown without waiting for full interval |
| Suppress when idle | Avoids Slack noise during overnight idle periods |
| Sequential loop only | Supervisor (parallel) mode is a separate concern; scope is bounded to the common case |
