# Design: Auto-Restart Pipeline Process When Pipeline Code Is Modified

## Overview

Enhance the auto-pipeline's existing hot-reload mechanism to detect source code
changes more promptly and restart the pipeline process gracefully, coordinating
with active child processes and the Slack listener to avoid interrupting work.

## Current State

The pipeline already has a basic hot-reload mechanism:

1. **Snapshot at startup**: `snapshot_source_hashes()` captures SHA-256 hashes
   of watched source files (`auto-pipeline.py`, `plan-orchestrator.py`)
2. **Check between items**: `check_code_changed()` compares current hashes
   against startup snapshot
3. **Self-restart**: On detection, calls `os.execv()` to replace the process
4. **Check points**: Only runs after completing a work item or resuming
   in-progress plans

### Gaps

- Detection only happens at discrete checkpoints (between work items). A long
  orchestrator run (30+ minutes) delays detection until completion.
- No periodic background check during idle wait periods.
- The `os.execv()` restart does not wait for Slack polling to drain cleanly.
- No Slack notification distinguishing "restart due to code change" from a
  fresh start.

## Design

### Approach: Background Thread Monitor

Add a lightweight background thread that periodically checks source file hashes
(reusing the existing `check_code_changed()` function). When a change is
detected, set a flag that the main loop and child process monitor can observe.

### Key Design Decisions

1. **Polling-based, not watchdog**: The existing `watchdog` dependency monitors
   backlog directories. Reusing it for source files would work but adds
   complexity. A simple polling thread checking hashes every N seconds is
   sufficient since source changes are infrequent (at most a few times per
   session).

2. **Graceful wait for child process**: When a code change is detected during
   an active orchestrator run, the pipeline sets a restart-pending flag but
   waits for the current child process to complete (or reach a safe stopping
   point) before restarting. This avoids killing the orchestrator mid-task.

3. **Immediate restart during idle**: When no work item is being processed
   (waiting for new items), the restart happens immediately since there is
   nothing to lose.

4. **Slack coordination**: Before `os.execv()`, stop background polling and
   send a notification. This is already partially implemented; we formalize it.

### Components

#### 1. CodeChangeMonitor class

A background thread that periodically calls `check_code_changed()` and sets a
threading.Event when a change is detected.

- Poll interval: configurable, default 10 seconds
- Uses existing `_startup_file_hashes` and `check_code_changed()`
- Thread is daemon so it does not block process exit
- Exposes `restart_pending` event for main loop to check

#### 2. Enhanced main_loop integration

- Replace the two inline `check_code_changed()` call sites with checks on
  `monitor.restart_pending`
- Add a check in the idle wait (`new_item_event.wait()`) so the pipeline
  restarts promptly when idle
- Add a check after each `execute_plan()` call (already exists, just
  refactored)

#### 3. Graceful restart procedure

Formalize the restart sequence (already partially exists):

1. Log the restart reason
2. Send Slack notification
3. Print and write session usage summary
4. Stop Slack background polling
5. Stop filesystem observer
6. Restore terminal settings
7. `os.execv()` to restart

Extract this into a `_perform_restart()` helper to avoid code duplication
across the 2-3 restart call sites.

### Files to Modify

- `scripts/auto-pipeline.py` - Add `CodeChangeMonitor` class, refactor restart
  logic, integrate monitor into main loop
- `tests/test_auto_pipeline.py` - Add tests for `CodeChangeMonitor`

### Files Unchanged

- `scripts/plan-orchestrator.py` - No changes needed; the orchestrator is a
  child process managed by auto-pipeline

### Constants

- `CODE_CHANGE_POLL_INTERVAL_SECONDS = 10` - How often the monitor checks
- Reuses existing `HOT_RELOAD_WATCHED_FILES` list

### Error Handling

- If `os.execv()` fails (e.g., script was deleted), log the error and exit
  with code 1 rather than entering a broken state
- Monitor thread catches all exceptions to avoid crashing the pipeline

## Testing Strategy

- Unit test `CodeChangeMonitor` start/stop/detection using temp files
- Unit test `_perform_restart()` helper (mock os.execv)
- Verify existing hot-reload tests still pass
