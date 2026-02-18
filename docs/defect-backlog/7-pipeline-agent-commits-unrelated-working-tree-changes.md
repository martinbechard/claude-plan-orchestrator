# Pipeline agent commits unrelated working-tree changes

## Status: Open

## Priority: High

## Summary

When a pipeline sub-agent commits its work, it stages the entire file with
git add, which includes uncommitted changes made by other sessions (human edits,
other agents). This results in misleading commits that silently include unrelated,
unreviewed code changes.

## Observed Behavior

Commit 789d325 ("Add 5 Whys validation and retry logic to intake analysis") was
created by a pipeline sub-agent working on 5 Whys retry logic. However, it also
committed LLM routing changes (MESSAGE_ROUTING_PROMPT, _route_message_via_llm,
_execute_routed_action, deletion of classify_message) that were being edited in a
separate concurrent session. The commit message does not mention the routing changes.

## Root Cause

The sub-agent task prompt (line ~2244 in plan-orchestrator.py) instructs: "Commit
your changes with a descriptive message." The sub-agent then runs git add on files
it modified, but git add stages the entire file contents, not just the agent's own
changes. Any concurrent edits to the same file get committed silently.

## Affected Code Paths

1. Sequential task execution (run_claude_task at line ~4530): sub-agent runs in
   the main worktree with full access to uncommitted changes
2. The sub-agent prompt at line ~2244 gives no guidance about checking for
   unrelated changes before committing

## Recommended Fix

Stash-before-task pattern: before spawning the sub-agent, run git stash to save
any uncommitted working-tree changes. After the agent finishes, restore them with
git stash pop. This guarantees the agent only sees a clean working tree plus its
own changes.

Implementation:
- In the task execution path (around line 4530), before calling run_claude_task:
  1. Run git stash --keep-index to save uncommitted changes
  2. Record whether a stash was created (check git stash list)
  3. Run the sub-agent task
  4. After completion, run git stash pop to restore prior changes
- Handle stash pop conflicts gracefully (log warning, keep stash for manual resolution)

## Source

Discovered during investigation of uncommitted changes after implementing LLM
message routing feature (2026-02-17).

## Verification Log

### Verification #1 - 2026-02-17 19:44

**Verdict: PASS**

**Checks performed:**
- [x] Build passes (py_compile for both scripts succeeds)
- [x] Unit tests pass (189 passed in 2.64s)
- [x] git_stash_working_changes() stashes uncommitted changes before task (line 4564)
- [x] git_stash_pop() restores changes in finally block after task (line 4747)
- [x] Stash uses --include-untracked to capture untracked files (line 1478)
- [x] Stash pop conflict handled gracefully with warning (lines 1504-1506)
- [x] Stash is only attempted when not in dry_run mode (line 4563)
- [x] 5 dedicated stash unit tests pass (clean tree, dirty tree, stash fails, pop success, pop conflict)

**Findings:**
- The fix implements the recommended stash-before-task pattern exactly as described in the defect.
- git_stash_working_changes() at plan-orchestrator.py:1449 checks for dirty tree (unstaged, staged, and untracked files) before stashing. Uses ORCHESTRATOR_STASH_MESSAGE constant for identifiable stash entries.
- git_stash_pop() at plan-orchestrator.py:1490 restores changes, with graceful fallback on conflict (stash preserved for manual resolution, stderr logged).
- Integration in sequential task loop: stash created at line 4564 before run_claude_task, restored at line 4747 inside a finally block ensuring restoration even on task failure.
- The reported symptom (agent committing unrelated working-tree changes from concurrent sessions) is addressed: the stash isolates the working tree so the agent only sees a clean tree plus its own modifications.
