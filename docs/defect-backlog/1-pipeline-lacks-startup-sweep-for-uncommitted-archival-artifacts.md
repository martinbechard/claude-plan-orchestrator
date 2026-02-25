# Pipeline lacks startup sweep for uncommitted archival artifacts

## Status: Open

## Priority: Medium

## Summary

When the pipeline is interrupted (SIGINT, SIGTERM, crash) between `shutil.move` and `git commit` inside `archive_item()`, moved files are left uncommitted with no recovery mechanism. Add a startup sweep function that runs before the main processing loop: it should detect uncommitted changes in `docs/completed-backlog/`, `docs/defect-backlog/`, `docs/feature-backlog/`, and `.claude/plans/`, then commit them as a batch recovery commit. Additionally, the signal handler at line 3191 should attempt to commit any in-flight archive changes before exiting.

## 5 Whys Analysis

  1. **Why were there uncommitted files in the repo?** Because prior pipeline sessions moved backlog items to their completed directories (and deleted a plan YAML) but never committed those changes to git.
  2. **Why didn't the pipeline commit those changes?** Because the pipeline was interrupted (via SIGINT/SIGTERM or a crash) after the file-move step (`shutil.move`) in `archive_item()` but before or during the `git commit` subprocess call at line 2115-2118.
  3. **Why does an interruption between move and commit cause permanent orphaning?** Because `archive_item()` performs the filesystem move and the git commit as two separate, non-atomic steps — if the process dies between them, the moved file is on disk but not in git, and nothing retries.
  4. **Why doesn't the pipeline detect and fix these orphaned changes on the next startup?** Because `main()` and the startup sequence have no recovery step that checks for uncommitted/untracked files in the archival directories (`docs/completed-backlog/`, `.claude/plans/`) before entering the processing loop.
  5. **Why was no startup recovery ever implemented?** Because the archive workflow was designed assuming each `archive_item()` call runs to completion, and the edge case of mid-archive interruption — which the signal handler makes likely by calling `sys.exit(0)` at line 3211 without flushing pending git operations — was not accounted for.

**Root Need:** The pipeline needs an atomic-or-recoverable archive workflow — either making file-move + git-commit atomic, or adding a startup sweep that detects and commits any orphaned archival artifacts left by prior interrupted sessions.

## Source

Created from Slack message by U0AEWQYSLF9 at 1771977146.183899.

## Verification Log

### Verification #1 - 2026-02-24 22:30

**Verdict: PASS**

**Checks performed:**
- [x] Build passes (py_compile on both scripts)
- [x] Unit tests pass (388 passed in 2.69s)
- [x] Startup sweep function exists and detects uncommitted archival artifacts
- [x] Startup sweep is called before main processing loop
- [x] Signal handler commits in-flight archive changes before exiting
- [x] All required directories are scanned

**Findings:**
- py_compile passes for both scripts/auto-pipeline.py and scripts/plan-orchestrator.py with no errors.
- All 388 unit tests pass (pytest 8.3.5, Python 3.11.10).
- _collect_archival_paths() (line 157) parses git status --porcelain output and filters for files in archival directories (ARCHIVAL_SWEEP_DIRS). Handles rename entries correctly.
- sweep_uncommitted_archival_artifacts() (line 176) runs git status, collects archival paths, stages them with git add, and creates a single batch recovery commit with message "chore: recover uncommitted archival artifacts from interrupted pipeline". Gracefully handles git failures.
- The sweep is called at line 3353 in main(), after ensure_directories() and write_pid_file() but before main_loop() -- exactly as the defect requested.
- handle_signal() (line 3257) now includes a best-effort block (lines 3273-3294) that checks git status for in-flight archival artifacts and commits them before calling sys.exit(0). Wrapped in try/except to ensure shutdown completes even if commit fails.
- ARCHIVAL_SWEEP_DIRS (line 92) covers: docs/defect-backlog/, docs/feature-backlog/, docs/analysis-backlog/, docs/completed-backlog/, .claude/plans/ -- all directories mentioned in the defect plus docs/analysis-backlog/.
- Dedicated unit tests exist: 8 tests for _collect_archival_paths(), 4 tests for sweep_uncommitted_archival_artifacts(), and 3 tests for handle_signal() commit behavior. All pass.
