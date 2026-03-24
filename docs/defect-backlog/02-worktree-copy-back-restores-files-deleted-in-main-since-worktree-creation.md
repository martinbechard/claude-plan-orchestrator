# Worktree copy-back restores files that were deleted in main after the worktree was created

## Status: Open

## Priority: High

## Summary

When a task runs in a git worktree, the worktree is branched from main at creation
time. If files are deleted from main while the task is running, the worktree still
contains those files. When the executor copies the worktree's results back to main
(the "added/modified files" pass in `git.py`), it treats those stale files as
additions and writes them back — silently undoing the deletions that happened in main
while the task was in flight.

## Observed Incident

2026-03-24 16:49: commit `edf6f2a2` ("chore: archive defect 01-bug") re-created
`docs/feature-backlog/16-least-privilege-agent-sandboxing.md` and
`docs/feature-backlog/17-read-only-analysis-task-workflow.md` with 128 lines of
content. Both files had been deleted from feature-backlog at 12:36 by the pipeline's
own archival commits. The worktree for defect-01 was created before 12:36, so it
carried the pre-deletion snapshot. Its copy-back pass treated the files as worktree
additions and wrote them back to main.

## Root Cause

The worktree copy-back logic in `git.py` identifies files to copy by diffing the
worktree against its base commit (`git diff base..HEAD --name-status`). Files that
existed in the base commit and were unchanged in the worktree are correctly excluded.
But files that existed in the base commit, were unchanged in the worktree, AND were
deleted from main after the worktree was created are not excluded — because the diff
only compares worktree HEAD against the worktree's own base, not against current main.

```
main at worktree creation:  feature-backlog/16.md  ← worktree base contains this
main at copy-back time:     (deleted)              ← main no longer has it
worktree HEAD:              feature-backlog/16.md  ← unchanged; not in diff output
copy-back logic:            skips it (not in diff) ← correct
... BUT "added" files pass also copies all files present in worktree? ← investigate
```

The exact copy path needs verification — either the copy-back copies all files (not
just diff'd ones) or the diff baseline is wrong (diffing against an ancestor that
predates the deletion).

## Fix

Before writing each file from the worktree to main, check whether the file was
explicitly part of the task's changes (present in `git diff base..HEAD`) AND whether
the destination path still exists in main's current HEAD. If the destination was
deleted in main after the worktree was created, skip the copy. Alternatively, rebase
the worktree onto current main before the copy-back pass so the diff correctly
excludes files that main has already removed.

Relevant code: `langgraph_pipeline/shared/git.py` — the section described as
"Copies added/modified files from the worktree into main."

## Source

Root-caused on 2026-03-24 from commit `edf6f2a2` which re-created two feature-backlog
files that had been deleted four hours earlier by the pipeline itself.
