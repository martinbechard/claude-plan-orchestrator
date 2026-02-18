# Design: Persistent Logging System with Per-Item Detail Files and Summary Progress Log

## Overview

Implement a two-tier logging system in `auto-pipeline.py` and `plan-orchestrator.py`:

- **Tier 1 (detail logs):** `logs/<item-slug>.log` — one file per backlog item,
  capturing every console line for that item's full lifecycle. Appends across
  restarts with timestamped session headers so multiple runs are preserved.
- **Tier 2 (summary log):** `logs/pipeline.log` — top-level file recording only
  summary events: item started, item completed, warnings, and errors.

All existing `print()` calls route through a thin logging facade so **no call-site
changes are required**.

## Problem Statement

The pipeline runs autonomously. Console output is ephemeral — once the terminal
session ends or scrolls, diagnostic information is lost. Re-running is expensive
and non-deterministic. Operators need durable, structured audit trails organized
by work item.

## Architecture

### Directory layout

```
logs/
  pipeline.log                      # summary events (all items)
  1-feature-slug.log                # detail log for item 1
  2-defect-slug.log                 # detail log for item 2
  ...
```

The `logs/` directory lives at the project root. It is created on first use.

### Logging facade in `auto-pipeline.py`

A module-level `_item_log_file: Optional[TextIO]` field holds the currently-open
detail log file. The existing `log()` and `verbose_log()` functions are extended
to write to `_item_log_file` (if open) in addition to stdout.

A new `PipelineLogger` context manager (or pair of functions
`open_item_log(slug)` / `close_item_log()`) handles file lifecycle:

1. Before `process_item()`: open `logs/<slug>.log` in append mode,
   write a session-start header (timestamp, PID, item name).
2. Redirect all `log()` and `verbose_log()` output to the file as well.
3. After `process_item()` returns (success or failure): write a session-end
   footer, then close and release the file handle.

The summary log `logs/pipeline.log` receives only high-level events:
item started, item completed, item failed, verification cycle count, and
any WARNING/ERROR lines.

### Logging facade in `plan-orchestrator.py`

`plan-orchestrator.py` is invoked as a subprocess by `auto-pipeline.py`.
Its stdout/stderr are already captured and re-printed line-by-line by the
parent process (the `prefix_output()` helper at line ~262 in `auto-pipeline.py`).
Therefore, per-item detail logging for orchestrator output is **inherited
automatically** through the parent's log() facade.

No changes are required in `plan-orchestrator.py` for the core logging feature.
If a task-level log for orchestrator internals is desired in the future it can
be a separate feature.

### Session header format

```
================================================================================
SESSION START  2026-02-18 14:23:01  PID=12345
Item: 1-persistent-logging-system-with-per-item-detail-files-and-summary-progress-log
Type: feature
================================================================================
```

### Session footer format

```
================================================================================
SESSION END  2026-02-18 14:51:22  duration=1701s  result=success
================================================================================
```

### Summary log format

Each summary line is a single timestamped structured record:

```
2026-02-18 14:23:01 [INFO]  STARTED  1-feature-slug (feature)
2026-02-18 14:51:22 [INFO]  COMPLETED  1-feature-slug (feature)  duration=1701s
2026-02-18 14:51:22 [WARN]  VERIFICATION_CYCLE  1-feature-slug  cycle=2/3
2026-02-18 14:51:22 [ERROR] FAILED  1-feature-slug  phase=orchestrator
```

## Key Files

| File | Change |
|------|--------|
| `scripts/auto-pipeline.py` | Add `_open_item_log()`, `_close_item_log()`, `_log_summary()` helpers; extend `log()` and `verbose_log()` to tee to item log; wrap `process_item()` calls with log lifecycle |
| `logs/` | Created automatically at runtime; `.gitignore` entry added |
| `tests/test_auto_pipeline.py` | Tests for log open/close/tee behavior and summary events |

## Design Decisions

- **`logs/` at project root, not `.claude/`.** Log files are user-facing
  operational artifacts; placing them in `.claude/` (an internal directory)
  would make them harder to discover. The root-level `logs/` mirrors common
  conventions (Django, Node, etc.).
- **Append mode, not overwrite.** Each run appends to the existing file with
  a timestamped session header. This preserves the full history of all attempts
  for a given item, which is critical for diagnosing intermittent failures.
- **`plan-orchestrator.py` unchanged.** Its output is already captured and
  re-emitted by the parent process. Duplicating a logging layer inside the
  orchestrator would create complex coupling between parent and child processes.
- **No Python `logging` module.** The existing codebase uses raw `print()` for
  all output. Switching to the `logging` module would require changing 194+
  call sites. Instead, a minimal tee in `log()` / `verbose_log()` achieves the
  same result with zero call-site impact.
- **`_item_log_file` global, not threaded.** `process_item()` runs sequentially
  in the main thread; only one item is processed at a time. A simple module-level
  global is sufficient.
- **Summary log written by `auto-pipeline.py` only.** Summary events are
  pipeline-level decisions (start, end, fail) that only `auto-pipeline.py`
  makes. This keeps the summary log focused and avoids duplicating
  orchestrator sub-events.
- **`.gitignore` entry for `logs/`.** Log files are runtime artifacts and
  should not be committed.
