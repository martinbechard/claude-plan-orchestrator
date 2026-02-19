# Auto-stash creates self-inflicted merge conflicts on plan YAMLs

## Status: Open

## Priority: High

## Summary

The git_stash_working_changes() / git_stash_pop() mechanism creates merge
conflicts on plan YAML files because the orchestrator stashes the YAML before
each task, the agent commits updates to the same YAML during execution, and the
subsequent stash pop fails due to diverged content.

## Observed Behavior

During the plan-17 pipeline run, the auto-stash mechanism stashed the plan YAML
before a task. The agent then committed updates to the same YAML (marking tasks
completed). When git_stash_pop() ran, it failed because the stashed version and
the committed version had diverged. The recovery code (git checkout . + git stash
drop) did not fully resolve the merge state, leaving UU (unresolved) conflict
markers. Two separate "resolve merge conflicts" commits were required to recover
(commits 104a881 and c0b0135, following the stash commit b3b3dde).

## Root Cause

git_stash_working_changes() at line 1792 stashes all uncommitted changes
including .claude/plans/*.yaml files. The agent then commits new content to the
same YAML during task execution. git_stash_pop() at line 1833 encounters a merge
conflict because the file has been modified on both sides (stash and HEAD).

The recovery path at lines 1862-1864 runs git checkout . followed by git stash
drop, but this does not fully clear merge conflict state. A git checkout . on a
file with UU status may leave conflict markers or fail silently, and the merge
state persists until explicitly resolved with git reset or git merge --abort.

## Affected Code Paths

1. scripts/plan-orchestrator.py line 1792: git_stash_working_changes() stashes
   the plan YAML along with other working-tree changes
2. scripts/plan-orchestrator.py line 1833: git_stash_pop() fails when the YAML
   has been committed to by the agent
3. scripts/plan-orchestrator.py lines 1862-1864: recovery code does not fully
   resolve merge state

## Recommended Fix

Option A (preferred): Exclude plan YAMLs from stash by using pathspec:
   git stash push --include-untracked -m "..." -- . ":(exclude).claude/plans/"

Option B: Improve recovery to use git reset --merge before checkout:
   subprocess.run(["git", "reset", "--merge"], capture_output=True)
   This clears the merge state that git checkout . alone does not resolve.

Option C: Combine both approaches for defense in depth.

## Source

Discovered during feature-19 pipeline run analysis (2026-02-19). Evidence from
plan-17 execution: commit b3b3dde (orchestrator-auto-stash modified plan-17
YAML), followed by merge conflict resolution commits 104a881 and c0b0135.

## Verification Log

### Verification #1 - 2026-02-19 18:18

**Verdict: PASS**

**Checks performed:**
- [x] Build passes (py_compile on both scripts succeeded with no errors)
- [x] Unit tests pass (309 passed in 2.82s, 0 failures)
- [x] Plan YAMLs excluded from stash (Option A implemented)
- [x] Recovery uses git reset --merge before checkout (Option B implemented)
- [x] Both fixes covered by unit tests

**Findings:**

1. **Plan YAML exclusion (Option A):** Constant STASH_EXCLUDE_PLANS_PATHSPEC = ":(exclude).claude/plans/" defined at line 46 of plan-orchestrator.py. The git_stash_working_changes() function at line 1819-1821 passes this pathspec to the stash push command: ["git", "stash", "push", "--include-untracked", "-m", ORCHESTRATOR_STASH_MESSAGE, "--", ".", STASH_EXCLUDE_PLANS_PATHSPEC]. This prevents plan YAMLs from being stashed, eliminating the root cause of the conflict.

2. **Improved recovery (Option B):** The git_stash_pop() recovery path at line 1865 now calls git reset --merge before git checkout . (line 1866) and git stash drop (line 1867). The comment at line 1862-1863 explains that git reset --merge must precede git checkout . to clear UU (unmerged) index state.

3. **Test coverage:** test_git_stash_working_changes_dirty_tree (line 691) verifies STASH_EXCLUDE_PLANS_PATHSPEC is in the stash command. test_git_stash_pop_conflict (line 728) verifies reset --merge is called before checkout. test_git_stash_pop_conflict_calls_reset_merge (line 742) verifies the exact recovery sequence: reset --merge, checkout ., stash drop.

4. **Fix commit:** 2d25cea "fix: exclude plan YAMLs from stash and improve conflict recovery" implements Option C (both approaches combined for defense in depth).

The reported symptom (plan YAMLs being stashed and causing merge conflicts on pop) is fully addressed by both preventing the stash and properly recovering if a conflict does occur.
