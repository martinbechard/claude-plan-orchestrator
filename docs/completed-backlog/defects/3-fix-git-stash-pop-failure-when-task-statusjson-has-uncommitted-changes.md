# Fix git stash pop failure when task-status.json has uncommitted changes

## Status: Open

## Priority: Medium

## Summary

After a section completes, the orchestrator writes to `.claude/plans/task-status.json` to record phase completion but does not commit this change before calling `git stash pop`. The stash pop then fails with a merge conflict because the working tree already has changes to that file. The fix should either commit orchestrator-managed files before stash pop, or use `git checkout -- task-status.json` to discard the conflicting local changes (since the stash will restore the correct state), or restructure the write order so task-status.json is only updated after the stash pop succeeds.

## 5 Whys Analysis

  1. **Why does `git stash pop` fail?** Because `task-status.json` has local uncommitted changes that conflict with the stash being popped.
  2. **Why does `task-status.json` have uncommitted changes at stash-pop time?** Because the orchestrator writes to `task-status.json` during task execution (to track task state) but does not commit those changes before attempting `git stash pop`.
  3. **Why are task-status.json changes not committed before stash pop?** Because the stash/pop lifecycle (stash before subagent work, pop after) does not account for files the orchestrator itself modifies during the session — only the subagent's changes are expected to be stashed/popped.
  4. **Why does the orchestrator write to task-status.json without committing it first?** Because task-status.json is used as a live progress-tracking file during execution, and the design assumes it will be committed as part of plan commits (e.g., "plan: Task X completed"), but the stash pop happens *after* a plan commit, when a subsequent write to task-status.json may have already occurred.
  5. **Why does a subsequent write to task-status.json occur after the plan commit but before stash pop?** Because the section-completion handler writes to task-status.json to mark phase completion, and this write is not followed by a commit before the stash pop that cleans up the subagent's working state.

**Root Need:** The stash/pop lifecycle needs to either commit or discard orchestrator-owned files (like task-status.json) before popping, or the stash strategy needs to exclude files the orchestrator manages directly.

## Source

Created from Slack message by U0AEWQYSLF9 at 1771420608.534969.

## Verification Log

### Verification #1 - 2026-02-18 09:00

**Verdict: PASS**

**Checks performed:**
- [x] Build passes (Python syntax check for both scripts)
- [x] Unit tests pass (214/214)
- [x] Fix present: git checkout discard block exists in git_stash_pop() before git stash pop call
- [x] Discard block appears BEFORE the git stash pop call
- [x] Regression test test_stash_pop_discards_task_status_json passes
- [x] Orchestrator dry-run completes without errors

**Findings:**
- Syntax check: `python3 -c "import py_compile; py_compile.compile('scripts/auto-pipeline.py', doraise=True); py_compile.compile('scripts/plan-orchestrator.py', doraise=True)"` → "syntax OK"
- Full test suite: 214 passed in 2.68s with no failures
- Fix confirmed at scripts/plan-orchestrator.py line 1510-1516: `git checkout -- STATUS_FILE_PATH` block is present inside git_stash_pop() before the `git stash pop` subprocess call at line 1518
- grep output: `1514:            ["git", "checkout", "--", STATUS_FILE_PATH],` confirming the checkout line
- grep -A2 "Discard task-status" confirms discard block at line 1510 precedes git stash pop at line 1518
- Regression test test_stash_pop_discards_task_status_json (tests/test_plan_orchestrator.py) reproduces the bug scenario (stash WIP, write task-status.json post-stash, then verify git_stash_pop() returns True and WIP file is restored) — PASSED
- Orchestrator dry-run: `python3 scripts/plan-orchestrator.py --plan .claude/plans/sample-plan.yaml --dry-run` completes cleanly with "Result: SUCCESS"
