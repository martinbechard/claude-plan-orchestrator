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
