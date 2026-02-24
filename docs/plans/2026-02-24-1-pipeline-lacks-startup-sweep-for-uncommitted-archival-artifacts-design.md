# Design: Pipeline Startup Sweep for Uncommitted Archival Artifacts

## Problem

When auto-pipeline.py is interrupted (SIGINT, SIGTERM, crash) between
shutil.move and git commit inside archive_item(), moved files are left
uncommitted. There is no recovery mechanism to detect and commit these
orphaned artifacts on the next startup.

## Architecture

### Component 1: Startup Sweep Function

Add sweep_uncommitted_archival_artifacts() to scripts/auto-pipeline.py.

Behavior:
- Run git status --porcelain to detect uncommitted changes
- Filter results to only the archival directories:
  - docs/completed-backlog/
  - docs/defect-backlog/
  - docs/feature-backlog/
  - docs/analysis-backlog/
  - .claude/plans/
- If matching uncommitted changes are found, stage them and create a
  single batch recovery commit
- Log the recovery action for visibility

Call site: main() function, after ensure_directories() and write_pid_file()
but before main_loop(). This ensures recovery happens once at startup before
any new processing begins.

### Component 2: Signal Handler Enhancement

Modify handle_signal() at line 3191 to attempt committing any in-flight
archive changes before exiting.

Behavior:
- After terminating the active child process, check git status for
  uncommitted changes in the archival directories
- If found, attempt to stage and commit them
- Use a try/except to avoid blocking shutdown if the commit fails
- This reduces the window where interruption leaves orphaned artifacts

### Component 3: Unit Tests

Add tests for both components in tests/test_auto_pipeline.py:
- Test that sweep detects and commits uncommitted archival files
- Test that sweep is a no-op when there are no uncommitted changes
- Test that the signal handler attempts commit before exit

## Key Files

- scripts/auto-pipeline.py - main implementation (sweep function, signal handler, main() integration)
- tests/test_auto_pipeline.py - unit tests

## Design Decisions

1. Single batch commit: Rather than one commit per orphaned file, use a
   single recovery commit to minimize git overhead and keep history clean.

2. Startup-only sweep: Running the sweep only at startup (not periodically)
   keeps the design simple and avoids interference with normal processing.

3. Best-effort signal handler commit: The signal handler commit is
   best-effort -- if it fails, the startup sweep on next run will catch it.

4. Reuse existing constants: The directories to check are already defined
   as DEFECT_DIR, FEATURE_DIR, ANALYSIS_DIR, COMPLETED_DIRS, and PLANS_DIR.
