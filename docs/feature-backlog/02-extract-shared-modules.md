# Extract Shared Modules

## Status: Open

## Priority: High

## Summary

Extract duplicated and shared logic from auto-pipeline.py and plan-orchestrator.py
into langgraph_pipeline/shared/. These become importable modules used by both the
existing scripts and the future LangGraph graph nodes. This eliminates the
importlib.util hack in auto-pipeline.py that loads the entire 5,879-line orchestrator
as a side effect to import 8 symbols.

## Scope

### Modules to Extract

#### shared/rate_limit.py
Extract rate limit detection and wait calculation. Currently duplicated in both scripts:
- parse_rate_limit_reset_time() -- parses "Please try again after HH:MM:SS" from output
- check_rate_limit() -- scans output lines for rate limit indicators
- wait_for_rate_limit_reset() -- sleeps until the parsed reset time

Both scripts must import from this single module after extraction.

#### shared/claude_cli.py
Extract Claude CLI subprocess management:
- OutputCollector class (duplicated in both scripts with identical logic)
- run_child_process() / run_claude_task() common subprocess patterns
- Output streaming and log capture

#### shared/git.py
Extract git operations:
- git_stash_working_changes() / git_stash_pop()
- get_worktree_path() / create_worktree() / cleanup_worktree()
- copy_worktree_artifacts()
- Git commit helpers

#### shared/config.py
Extract configuration loading:
- load_orchestrator_config() from .claude/orchestrator-config.yaml
- Config path constants
- Default value handling

#### shared/budget.py
Extract budget tracking:
- BudgetGuard / PipelineBudgetGuard (merge into one)
- SessionUsageTracker / PlanUsageTracker (merge into one with scope parameter)
- BudgetConfig dataclass

#### shared/paths.py
Centralize path constants:
- ORCHESTRATOR_CONFIG_PATH
- PLANS_DIR, BACKLOG_DIRS, COMPLETED_DIRS
- STATUS_FILE_PATH, TASK_LOG_DIR
- PID_FILE_PATH

### Migration Approach

1. Create each shared module with the extracted functions/classes
2. Update auto-pipeline.py to import from langgraph_pipeline.shared instead of using
   the importlib.util hack
3. Update plan-orchestrator.py to import from langgraph_pipeline.shared
4. Delete the importlib.util import block (lines 44-58 of auto-pipeline.py)
5. Run existing tests to verify no regressions
6. Add unit tests for each shared module in tests/langgraph/shared/

### Verification

- The importlib.util hack is gone from auto-pipeline.py
- Both scripts import from langgraph_pipeline.shared
- Existing tests pass without modification
- New unit tests cover each shared module
- No duplicated rate_limit / output_collector / git logic remains in the scripts

## Dependencies

- 01-langgraph-project-scaffold.md (needs the package structure to exist)

## Verification Log

### Task 2.1 - FAIL (2026-02-25 01:07)
  - Validator 'validator' failed to execute: No status file written by Claude
