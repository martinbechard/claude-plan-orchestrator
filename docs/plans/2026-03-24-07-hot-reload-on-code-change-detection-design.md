# Hot-Reload on Code Change Detection — Design

**Work item:** docs/feature-backlog/07-hot-reload-on-code-change-detection.md
**Date:** 2026-03-24

## Problem

The `langgraph_pipeline` CLI loads all Python modules once at startup and never picks up
code changes while running. The old `scripts/auto-pipeline.py` had a working hot-reload
feature (SHA-256 file hashing + background thread + `os.execv` restart) that was not
ported during the LangGraph rewrite.

## Architecture Overview

### New module: `langgraph_pipeline/shared/hot_reload.py`

Extracts all hot-reload primitives into a dedicated shared module following the existing
`langgraph_pipeline/shared/` convention. This keeps `cli.py` thin and makes the logic
independently testable.

Contents:
- `CODE_CHANGE_POLL_INTERVAL_SECONDS = 10` — polling constant
- `HOT_RELOAD_WATCHED_FILES` — list of `.py` files to monitor: all files under
  `langgraph_pipeline/` plus `scripts/auto-pipeline.py`
- `_compute_file_hash(filepath)` — SHA-256 of file contents; returns `""` on I/O error
- `snapshot_source_hashes()` — dict mapping each watched path to its current hash
- `check_code_changed(baseline)` — returns True if any hash differs from baseline
- `CodeChangeMonitor` — daemon thread; sets `restart_pending` event when change detected
- `_perform_restart()` — stops the monitor, removes PID file, calls `os.execv`

### Modified: `langgraph_pipeline/cli.py`

The continuous scan loop (`_run_scan_loop`) is the only mode that benefits from
hot-reload. Single-item (`--single-item`) and once (`--once`) modes exit naturally and
restart is irrelevant.

Changes:
1. Import `CodeChangeMonitor` and `_perform_restart` from `langgraph_pipeline.shared.hot_reload`
2. In `_run_scan_loop`, before the main `while` loop: create and start a `CodeChangeMonitor`
3. After each graph invocation (and after the quota-probe loop), check
   `code_monitor.restart_pending.is_set()` and call `_perform_restart(code_monitor)` if True
4. Stop the monitor in the `finally` block alongside Slack cleanup

### New test file: `tests/test_hot_reload.py`

Unit tests for all public functions in `hot_reload.py` using the same pytest conventions
as the existing test suite. Tests use `tempfile` for file I/O, monkeypatching for
`HOT_RELOAD_WATCHED_FILES`, and short `poll_interval` for `CodeChangeMonitor`.

## Key Files

| Path | Change |
|------|--------|
| `langgraph_pipeline/shared/hot_reload.py` | Create — all hot-reload utilities |
| `langgraph_pipeline/cli.py` | Modify — wire `CodeChangeMonitor` into `_run_scan_loop` |
| `tests/test_hot_reload.py` | Create — unit tests |

## Design Decisions

- **Safe restart boundary:** `restart_pending` is checked only between complete graph
  invocations, mirroring the quota-probe check. This prevents YAML state corruption.
- **`os.execv` restart:** Replaces the process in-place, preserving PID and environment,
  keeping the PID file valid. Same approach as `auto-pipeline.py`.
- **Daemon thread:** `CodeChangeMonitor` sets `daemon=True` so it never blocks process
  exit if the main thread exits first.
- **No restart in `--once` / `--single-item`:** These modes exit after one item; a
  restart would be confusing and wasted. Monitor is only started in the scan loop.
- **`HOT_RELOAD_WATCHED_FILES`:** Built at module import time using `glob.glob` over
  `langgraph_pipeline/` plus explicit scripts entries, so new files are picked up after
  a clean restart.
