# Chapter 9: Fixing the Parallel Merge

**Commit:** (2026-02-12, post-narrative)
**Change:** Replaced `merge_worktree()` with `copy_worktree_artifacts()`

## The Misdiagnosis

While writing the orchestrator narrative (Chapters 1-8), we examined the parallel merge
failures from the donation widget plan. The MEMORY.md rule said:

> "Parallel merge drops new files -- only copies YAML status, NOT new files from worktrees.
>  Avoid --parallel for phases creating new files."

But investigating the code revealed that `merge_worktree()` actually called
`git merge --no-ff`, which *should* bring all files. So why didn't it work?

## The Root Cause

The forensic evidence told the story. Commit `5757dd9` ("Parallel group 'phase-9-tests'
completed") had **one parent**, meaning it was a regular commit, not a merge commit.
The `git merge` never happened.

The root cause was a cascade of failures:

**Step 1: Multiple branches modify the YAML file.**
When parallel tasks run, each Claude session in each worktree commits changes. But the
prompt also instructs Claude to write to `task-status.json` and the orchestrator manages
the YAML plan. Both the parallel branches and the main branch touch `.claude/plans/`.

**Step 2: Sequential merging creates conflicts.**
The orchestrator merges branches one at a time. After merging branch A, HEAD advances.
Branch B was forked from the pre-merge HEAD, so its YAML changes conflict with the
post-merge state. The merge fails with `CONFLICT`.

**Step 3: Merge failure marks the task as failed.**
When `merge_worktree()` returned `(False, "Merge conflict...")`, the task was added
to `merge_failures`. But the worktree was still cleaned up, destroying the branch's
code changes.

**Step 4: Manual cherry-pick recovery.**
The developer had to `git cherry-pick` test files from the parallel branches that
were still lingering (not yet garbage-collected).

## The Fix: File-Copy Instead of Git Merge

The new `copy_worktree_artifacts()` function sidesteps git merge entirely:

```python
def copy_worktree_artifacts(worktree_path, task_id):
    branch_name = f"parallel/{task_id.replace('.', '-')}"
    SKIP_PREFIXES = (
        ".claude/plans/",
        ".claude/subagent-status/",
        ".claude/agent-claims"
    )

    # Find the fork point
    fork_point = git_merge_base(HEAD, branch_name)

    # Get changed files between fork point and branch tip
    for file in git_diff_name_status(fork_point, branch_name):
        # Skip coordination files -- orchestrator manages these
        if file starts with SKIP_PREFIXES:
            continue

        # Copy added/modified files from worktree to main
        if status in (Added, Modified, Copied):
            shutil.copy2(worktree/file, main/file)

        # Remove deleted files from main
        if status == Deleted:
            os.unlink(main/file)

        # Handle renames (copy new, delete old)
        if status == Renamed:
            shutil.copy2(worktree/new_path, main/new_path)
            os.unlink(main/old_path)

    return (True, summary, files_copied)
```

### Why This Works

1. **No YAML conflicts.** The SKIP_PREFIXES filter ensures coordination files are never
   copied from worktrees. The orchestrator writes the YAML state from its in-memory
   representation after all copies complete.

2. **No merge conflicts at all.** File copying is idempotent. If two tasks modify the
   same non-coordination file (which the conflict detector should prevent), the last
   copy wins. No git merge machinery involved.

3. **New files are handled correctly.** Added files are simply copied. The original
   `git merge` approach should have handled this too, but the cascading YAML conflict
   prevented it from ever reaching the new files.

4. **Renames and deletions are handled.** The `git diff --name-status` format includes
   R (rename) and D (delete) statuses, which the function processes correctly.

### The Single Combined Commit

Instead of one merge commit per branch, all copied files are staged and committed
in a single commit:

```python
# Separate added/modified files from deleted files
files_to_add = [f for f in all_copied if Path(f).exists()]
files_to_rm = [f for f in all_copied if not Path(f).exists()]

git add files_to_add ...
git rm --cached --ignore-unmatch files_to_rm ...

# Single commit for the entire parallel group
git commit -m "plan: Merge artifacts from parallel tasks 8.1, 8.2, 8.3"
```

Note the `git add` vs `git rm` split: deleted files no longer exist on disk, so
`git add` would fail on them. `git rm --cached --ignore-unmatch` stages the deletion
in the index without requiring the file to exist.

Then the orchestrator writes its YAML plan state and commits that separately (as before).
This produces a clean, readable history: one commit with all the code, one commit with
the plan state update.

### What Changed in the Calling Code

The parallel execution section was updated from:

```python
# OLD: git merge per branch
merge_success, merge_msg = merge_worktree(worktree_path, task_id)
```

To:

```python
# NEW: copy files, then single commit for all
copy_ok, copy_msg, copied_files = copy_worktree_artifacts(worktree_path, task_id)
all_copied_files.extend(copied_files)
# ... after all worktrees processed ...
git add all_copied_files
git commit -m "plan: Merge artifacts from parallel tasks ..."
```

## What This Enables

With this fix, the MEMORY.md rule "Avoid --parallel for phases creating new files" is
no longer needed. The `--parallel` flag is now safe for all task types:

- Tasks that create new files (tests, components, services)
- Tasks that modify existing files
- Tasks that rename or delete files
- Mixed groups of the above

The only remaining constraint is the pre-existing one: **parallel tasks should not
modify the same non-coordination files**, which the conflict detector already enforces.

## Questions

**Q: Could two parallel tasks both create a file with the same path?**
In theory, yes. The copy would succeed (last one wins), but one task's work would be
lost. The conflict detector doesn't catch this case because it only looks at files
mentioned in task descriptions, not files that might be created during execution. This
is an inherent limitation of static conflict detection. However, the YAML plan structure
makes this unlikely --- tasks in the same parallel group are designed to be independent.

**Q: Why not use `git checkout branch -- file` instead of file copy?**
That would work too and would be more "git-native." However, `shutil.copy2` is simpler,
doesn't require the branch to still exist, preserves file metadata, and avoids any
git index state issues. The branch is deleted after copying anyway.

**Q: What about file permissions?**
`shutil.copy2` preserves permissions (unlike `shutil.copy`). This matters for executable
scripts. The `2` in `copy2` specifically means "copy with metadata."
