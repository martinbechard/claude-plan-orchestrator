# Design: Fix git stash pop failure when task-status.json has uncommitted changes

## Defect Reference

docs/defect-backlog/3-fix-git-stash-pop-failure-when-task-statusjson-has-uncommitted-changes.md

## Problem Statement

After a section completes, the orchestrator writes `task-status.json` (STATUS_FILE_PATH)
to record the subagent's result. At the next task boundary, `git_stash_pop()` is called
in the `finally` block. If `task-status.json` is still present (uncommitted) in the
working tree, `git stash pop` fails with a conflict because the stash also contains a
version of that file.

The root cause is that `task-status.json` is an orchestrator-owned ephemeral file:

- Written by the subagent at end of task execution
- Read by `read_status_file()` immediately after the task finishes
- Cleared by `clear_status_file()` before the next task starts

However, `git_stash_working_changes()` runs before the status file is cleared, so the
file can be present and uncommitted when the stash is created. When `git stash pop`
runs in the `finally` block, the file is still in the working tree (it was stashed but
also remains from the orchestrator's write), causing a merge conflict.

## Architecture Overview

The fix is applied entirely in `scripts/plan-orchestrator.py` in two places:

### Fix 1 — Discard task-status.json before git stash pop

In `git_stash_pop()`, before invoking `git stash pop`, discard any uncommitted changes
to `STATUS_FILE_PATH` using `git checkout -- <path>`. This prevents a conflict because:

- `task-status.json` is ephemeral and orchestrator-owned (not user work)
- Its content has already been read by `read_status_file()` before we reach `git_stash_pop()`
- Discarding it before the pop gives git a clean slate for the file, allowing the stash pop to succeed

The discard is conditional: only execute `git checkout -- <path>` if the file is actually
present in the working tree (to avoid a git error when it does not exist).

### Fix 2 — Also exclude task-status.json from stash push (defense-in-depth)

Add `task-status.json` to `.gitignore` is NOT appropriate here because the file is
intentionally tracked in some contexts. Instead, the fix is purely behavioral in
`git_stash_pop()`.

## Key Files

| File | Change |
|------|--------|
| `scripts/plan-orchestrator.py` | Modify `git_stash_pop()` to discard `STATUS_FILE_PATH` before calling `git stash pop` |
| `tests/test_plan_orchestrator.py` | Add regression test verifying stash pop succeeds when task-status.json is present |

## Design Decisions

### Why discard in git_stash_pop() rather than before git_stash_working_changes()?

Discarding before the stash would cause `task-status.json` to not be stashed at all.
That is fine (since it's ephemeral), but it does not fully solve the problem: if the
orchestrator writes to `task-status.json` after the stash push (e.g., after reading
the result in `read_status_file()`), the file is still present during `git stash pop`.
Discarding immediately before `git stash pop` handles all timing scenarios.

### Why not commit task-status.json before stash pop?

Committing it would pollute the git history with ephemeral orchestrator state. The
file is intentionally transient — cleared before each task run.

### Why not restructure the write order?

The backlog item mentions restructuring as an option, but it would require significant
refactoring of the task-execution loop and introduce new timing risks. The targeted
discard approach is simpler, safer, and has minimal blast radius.

### Constant usage

The path `STATUS_FILE_PATH` is already a manifest constant at the top of the file.
The fix references it directly rather than introducing a new literal.
