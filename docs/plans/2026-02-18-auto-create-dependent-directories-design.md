# Auto-Create Dependent Directories - Design

## Overview

Both plan-orchestrator.py and auto-pipeline.py depend on several directories
existing at runtime. Currently, directories are created on-demand via scattered
mkdir calls in various functions, leading to inconsistency - some code paths
assume directories exist and fail if they don't.

This feature adds a centralized ensure_directories() function to each script,
called once at startup before any other logic, guaranteeing all required
directories exist.

## Architecture

### Pattern

Each script defines a REQUIRED_DIRS list of directory paths near its top-level
constants. A shared ensure_directories() function iterates this list, creating
any missing directories and logging which ones were created.

### plan-orchestrator.py

REQUIRED_DIRS:
- .claude/plans/ - plan YAML files
- .claude/plans/logs/ - task logs and usage reports
- .claude/subagent-status/ - parallel worker heartbeats
- logs/ - general logs
- logs/e2e/ - E2E test result logs

Called at the top of run_orchestrator() before loading the plan.

### auto-pipeline.py

REQUIRED_DIRS:
- .claude/plans/ - plan files
- logs/ - per-item detail logs and summary log
- docs/defect-backlog/ - monitored input directory
- docs/feature-backlog/ - monitored input directory
- docs/completed-backlog/features/ - archive destination
- docs/completed-backlog/defects/ - archive destination

Called in main() after argument parsing but before the main_loop() call.

### Cleanup of Redundant mkdir Calls

After ensure_directories() guarantees all directories exist, the following
scattered mkdir calls become redundant and should be removed:

auto-pipeline.py:
- os.makedirs(LOGS_DIR, ...) in _open_item_log()
- os.makedirs(LOGS_DIR, ...) in _log_summary()
- log_dir.mkdir(...) in write_session_report() of PipelineCostTracker
- os.makedirs(dest_dir, ...) in the archive function (keep this one - dest_dir
  is dynamic based on item type and is already in REQUIRED_DIRS, but the
  exist_ok=True call is harmless safety)

plan-orchestrator.py:
- TASK_LOG_DIR.mkdir(...) in save_usage_report()
- TASK_LOG_DIR.mkdir(...) in the task logging function

Note: mkdir calls that create directories NOT in REQUIRED_DIRS (like
worktree directories or dynamically-constructed paths) should be left alone.

## Design Decisions

1. Each script has its own REQUIRED_DIRS and ensure_directories() rather than
   a shared module, keeping the scripts self-contained as they are today.

2. Use os.makedirs(path, exist_ok=True) with parents=True behavior for
   nested paths like .claude/plans/logs/.

3. Log a [INIT] message for each directory created so users know what was
   missing. Silent if all directories already exist.

4. Do NOT remove the os.makedirs(dest_dir, ...) in the archive function since
   dest_dir could theoretically be changed by configuration in the future.

## Files Affected

- Modified: scripts/plan-orchestrator.py
- Modified: scripts/auto-pipeline.py
- Modified: tests/test_auto_pipeline.py (new tests for ensure_directories)
- Modified: tests/test_plan_orchestrator.py (new tests for ensure_directories)
