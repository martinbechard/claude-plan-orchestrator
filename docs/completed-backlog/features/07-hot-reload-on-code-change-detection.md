# Hot-reload pipeline on source code change detection

## Status: Open

## Priority: Medium

## Summary

The `langgraph_pipeline` CLI process loads all Python modules once at startup and never
picks up code changes while running. The old `scripts/auto-pipeline.py` had a
hot-reload feature (SHA-256 file hashing, background `CodeChangeMonitor` thread,
`os.execv` restart) that was not carried over to the LangGraph rewrite. Re-implementing
this in `langgraph_pipeline/cli.py` would let developers modify orchestrator code and
have the running pipeline restart itself automatically at the next safe checkpoint,
without requiring a manual stop/start cycle.

## 5 Whys Analysis

1. **Why does modifying source code not take effect in a running pipeline?** Because
   Python imports all modules into memory at process start; there is no reload mechanism
   in the current `langgraph_pipeline` entry point.
2. **Why is that a problem during development?** Because the pipeline is designed for
   long unattended runs; stopping it to pick up a fix means losing the current scan
   position, any in-flight quota wait, and queued backlog state.
3. **Why wasn't this carried over from the old pipeline?** The LangGraph rewrite focused
   on graph architecture; the hot-reload utility code from `auto-pipeline.py` was not
   migrated.
4. **Why not just restart manually?** Manual restarts interrupt autonomous operation and
   require the developer to be present — defeating the purpose of unattended overnight
   runs.
5. **Why is `os.execv` the right restart mechanism?** It replaces the process in-place,
   preserving the PID and inheriting the same environment and arguments, which keeps the
   PID file valid and avoids orphaned processes.

**Root Need:** Detect source file changes via SHA-256 hash comparison in a background
thread and trigger a clean `os.execv` self-restart at the next safe inter-task
boundary so code changes take effect without manual intervention.

## Implementation Notes

- The prior implementation in `scripts/auto-pipeline.py` is the reference: functions
  `_compute_file_hash`, `snapshot_source_hashes`, `check_code_changed`,
  `CodeChangeMonitor`, and `_perform_restart`, covered by `tests/test_auto_pipeline.py`.
- Watched files should be the `langgraph_pipeline/` package tree (all `.py` files) plus
  `scripts/auto-pipeline.py` and `langgraph_pipeline/cli.py`.
- The restart must only happen between backlog items (never mid-task) to avoid corrupting
  plan YAML state.
- The background monitor thread sets a `restart_pending` event; the main scan loop checks
  it before picking up the next item and calls `_perform_restart` if set.
- Poll interval and watched-file list should be constants, consistent with the existing
  `CODE_CHANGE_POLL_INTERVAL_SECONDS` pattern.

## Source

Requested by developer after confirming the feature was dropped in the LangGraph rewrite.
