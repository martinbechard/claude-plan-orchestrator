# Design: Pipeline Agent Commits Unrelated Working-Tree Changes

## Defect Reference
docs/defect-backlog/7-pipeline-agent-commits-unrelated-working-tree-changes.md

## Problem

When the orchestrator runs a sub-agent in sequential mode, the agent executes
in the main worktree. Any uncommitted changes (from human edits or other
sessions) are visible. When the agent runs git add on files it modified, the
entire file contents (including unrelated concurrent edits) are staged and
committed. This produces misleading commits containing unreviewed changes.

Parallel execution via worktrees is not affected because each worktree is
isolated by design.

## Architecture Overview

The fix adds a stash-before-task / pop-after-task pattern to the sequential
execution path in plan-orchestrator.py. Two new helper functions provide the
git stash mechanics, and the sequential task loop wraps each agent invocation
with stash/pop calls.

### Components

```
execute_plan()  (sequential path, line ~4490)
    |
    +-- git_stash_working_changes()     [NEW]
    |       runs: git stash push --include-untracked -m "orchestrator-auto-stash"
    |       returns: bool (True if stash was created)
    |
    +-- run_claude_task(prompt, ...)     [EXISTING, unchanged]
    |
    +-- git_stash_pop()                 [NEW]
            runs: git stash pop
            handles: conflict -> keep stash, log warning
```

### Key Files

| File | Change |
|------|--------|
| scripts/plan-orchestrator.py | Add git_stash_working_changes() and git_stash_pop() helpers; wrap sequential task execution with stash/pop |
| tests/test_plan_orchestrator.py | Add unit tests for stash helpers |

### Design Decisions

1. Use git stash push --include-untracked: This captures both modified tracked
   files and new untracked files. We do NOT use --keep-index because we want
   to hide all uncommitted state from the agent.

2. Unique stash message: Use a recognizable message like
   "orchestrator-auto-stash" so stash entries can be identified if manual
   cleanup is ever needed.

3. Stash creation detection: Check git stash list before and after to determine
   if a stash was actually created (git stash exits 0 even when there is
   nothing to stash in some git versions). Alternative: check exit code of
   git diff --quiet first.

4. Conflict handling on pop: If git stash pop fails (exit code non-zero), the
   stash is preserved. Log a warning so the human operator can resolve manually.
   Do not abort the plan - the agent's work was committed successfully.

5. Scope: Only the sequential execution path needs this fix. The parallel path
   already uses isolated worktrees.

6. Dry-run: Skip stash/pop during dry-run mode to avoid side effects.

### Sequence (Sequential Task Execution)

```
1. Orchestrator finds next pending task
2. Mark task as in_progress, save plan
3. [NEW] Call git_stash_working_changes()
   - If dirty tree: stash push, record stash_created=True
   - If clean tree: stash_created=False
4. Build prompt and execute run_claude_task()
5. [NEW] If stash_created: call git_stash_pop()
   - On success: working tree restored
   - On conflict: log warning, stash preserved
6. Process task result (success/failure/validation)
```

### Edge Cases

- No dirty state: git_stash_working_changes() returns False, pop is skipped
- Agent modifies same file as stashed changes: pop conflict, stash preserved
- Agent fails: stash still popped (we want human changes restored regardless)
- Plan save commits inside loop: save_plan only git-adds the plan YAML file,
  which is orchestrator-managed and not affected by the stash pattern
- Nested stashes: Not an issue since we only push one stash per task and pop
  it before the next task
