# Design: Hot-Reload Auto-Pipeline Code Without Disrupting Slack

## Problem

When auto-pipeline.py is running, code changes to auto-pipeline.py or
plan-orchestrator.py do not take effect until the process is manually restarted.
Restarting kills the Slack background poller, risking missed messages during
the gap.

## Architecture Overview

### Current State

- auto-pipeline.py runs a long-lived main_loop() in a single process
- SlackNotifier is imported once at module load via importlib.util
- plan-orchestrator.py runs as a subprocess (always gets fresh code)
- Slack poller runs as a daemon thread inside the same process
- The pipeline loop: scan -> create plan -> execute -> verify -> archive

### Key Observation

The plan-orchestrator subprocess always gets fresh code because it is launched
via subprocess.Popen. The real staleness problem is:

1. auto-pipeline.py own logic (scan, plan creation prompts, archive, etc.)
2. SlackNotifier class loaded at import time from plan-orchestrator.py

### Approach: File-Hash Check + os.execv Self-Restart

Between work items (after each process_item() call completes), check if the
source files have changed. If so, perform a graceful self-restart using
os.execv(), which replaces the current process image with a fresh one.

Why os.execv over importlib.reload:
- importlib.reload cannot safely reload the main script (__main__)
- Module-level constants, global state, and class definitions all need refresh
- os.execv is atomic: one process replaces another with the same PID
- The Slack poller daemon thread is automatically cleaned up (daemon=True)

### Self-Restart Flow

```
main_loop iteration:
  1. process_item(item)
  2. call check_code_changed()
     - compute SHA-256 of auto-pipeline.py and plan-orchestrator.py
     - compare against hashes captured at startup
  3. if changed:
     a. log("Code change detected. Restarting pipeline...")
     b. slack.stop_background_polling()  # graceful shutdown
     c. restore_terminal_settings()
     d. os.execv(sys.executable, [sys.executable] + sys.argv)
  4. else: continue to next item
```

### Handling Edge Cases

- Terminal corruption: restore_terminal_settings() before restart
- Slack gap: the poller has a 15s interval; restart takes <1s, so at worst
  one poll cycle is delayed
- In-progress plans: the pipeline already handles recovery of in-progress
  plans on restart via find_in_progress_plans() and reset_interrupted_tasks()
- Failed items tracking: lost on restart, which is acceptable because
  failed_items is a session-level optimization; the pipeline already skips
  completed items via is_item_completed()
- --once mode: no restart needed (exits after one item anyway)
- --dry-run mode: no restart needed (no long-running loop)
- Signal handlers: re-registered automatically since main() is re-entered

### Files to Modify

- scripts/auto-pipeline.py:
  - Add file hash computation at startup (snapshot_source_hashes)
  - Add check_code_changed() function
  - Add self-restart logic in main_loop after each work item
  - Update the SlackNotifier import to be reload-friendly

### Files NOT Modified

- scripts/plan-orchestrator.py: already runs as subprocess, no changes needed

## Design Decisions

1. Self-restart vs module reload: os.execv is simpler and more reliable than
   importlib.reload for main-script changes. It guarantees all module-level
   state is fresh.

2. Check frequency: only between work items (not during execution). This
   avoids interrupting active orchestrator runs while still picking up changes
   before the next item starts.

3. Hash-based detection: SHA-256 file hashing is fast and reliable. We hash
   both auto-pipeline.py and plan-orchestrator.py since both affect behavior.

4. Graceful Slack shutdown: stop_background_polling() before restart ensures
   no in-flight API calls are interrupted. The new process re-creates the
   SlackNotifier and starts polling again.

5. Session state loss is acceptable: failed_items set and session_tracker
   are lost on restart, but this is fine because (a) failed items are skipped
   via file-level status checks and (b) usage tracking is per-session by design.
