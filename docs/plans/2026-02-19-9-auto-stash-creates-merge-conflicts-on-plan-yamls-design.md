# Design: Fix Auto-Stash Merge Conflicts on Plan YAMLs

## Problem

git_stash_working_changes() stashes all uncommitted changes including
.claude/plans/*.yaml files. The agent then commits updates to the same YAML
(marking tasks completed). When git_stash_pop() runs, the stashed version and
committed version have diverged, causing a merge conflict.

The recovery path (git checkout . + git stash drop) does not fully clear merge
state, leaving UU (unresolved) conflict markers that require manual resolution.

## Affected Files

- scripts/plan-orchestrator.py
  - git_stash_working_changes() at line 1790
  - git_stash_pop() at line 1831
- tests/test_plan_orchestrator.py
  - Existing stash tests at lines 676-729

## Design: Defense in Depth (Option C)

Apply both fixes from the defect report for maximum reliability.

### Fix 1: Exclude plan YAMLs from stash (Prevention)

Change the git stash push command in git_stash_working_changes() to use
pathspec exclusion:

```
git stash push --include-untracked -m "orchestrator-auto-stash" -- . ":(exclude).claude/plans/"
```

This prevents the root cause entirely. Plan YAMLs are never stashed, so
there is nothing to conflict when the agent commits changes to them.

### Fix 2: Improve recovery with git reset --merge (Mitigation)

Change the recovery path in git_stash_pop() to clear merge state before
resetting the working tree:

```
git reset --merge      # clears merge state (UU -> clean)
git checkout .         # resets working tree to HEAD
git stash drop         # drops the stale stash entry
```

git checkout . alone cannot resolve files in UU (unmerged) status. Adding
git reset --merge first transitions the index out of the merge state, allowing
the subsequent checkout to succeed cleanly.

### Constant for Exclusion Pattern

Add a manifest constant for the exclusion pattern:

```
STASH_EXCLUDE_PLANS_PATHSPEC = ":(exclude).claude/plans/"
```

## Test Updates

Update existing tests in test_plan_orchestrator.py:

1. test_git_stash_working_changes_dirty_tree: verify the stash push command
   includes the pathspec arguments (-- . and the exclude pattern)

2. test_git_stash_pop_conflict: verify git reset --merge is called before
   git checkout . during recovery

3. New test: test_git_stash_pop_conflict_calls_reset_merge: verify the
   exact recovery command sequence (reset --merge, checkout ., stash drop)
