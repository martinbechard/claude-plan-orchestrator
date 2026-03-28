# Design: Worktree Copy-Back Restores Files Deleted in Main

**Date:** 2026-03-24
**Defect:** docs/defect-backlog/02-worktree-copy-back-restores-files-deleted-in-main-since-worktree-creation.md

## Architecture Overview

The worktree copy-back logic lives in `langgraph_pipeline/shared/git.py`,
function `copy_worktree_artifacts`. It diffs the worktree branch against the
fork point (`git diff --name-status fork_point branch_name`) and copies
added/modified files to main. The bug: when a file is changed in the worktree
AND deleted from main after the fork, the copy-back blindly writes it back,
silently undoing the deletion.

## Root Cause (Confirmed)

For any file with diff status A/M/C, the current code copies unconditionally:

```python
if status in ("A", "M", "C"):
    src = worktree_path / file_path
    dst = Path(file_path)
    if src.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(dst))   # ← no check against main HEAD
```

If main deleted the file after the worktree was created, `dst` is absent on
disk — but `copy2` will re-create it, undoing the deletion.

## Fix

Add a `_file_exists_in_ref` helper and guard each A/M/C copy with a
two-condition check:

1. Did the file exist at `fork_point`? (`git cat-file -e fork_point:path`)
2. Does it still exist in main `HEAD`? (`git cat-file -e HEAD:path`)

If (1) is **true** and (2) is **false**, main intentionally deleted the file
after the fork — skip copying it and log a warning.

Files that are genuinely new (not in fork_point) continue to be copied
normally. Files deleted by the worktree task (status D) are unaffected.

## Key Files

| File | Change |
|------|--------|
| `langgraph_pipeline/shared/git.py` | Add `_file_exists_in_ref`, guard A/M/C copy loop |
| `tests/langgraph/shared/test_git.py` | Add tests for the skip behavior; update existing tests whose `subprocess.run` side-effects need the extra `cat-file` calls |

## Design Decisions

- Use `git cat-file -e` (object existence check, no output) — cheapest git
  query for existence; no parsing needed.
- Only apply the guard for A/M/C (add/modify/copy). D (delete) is unchanged.
  R (rename) copies the new path; apply the same guard to the new path.
- Skipped files are appended to `files_skipped` and included in the summary
  message so the operator can see what was suppressed.
- The helper `_file_exists_in_ref` is module-private (leading underscore)
  since it only supports `copy_worktree_artifacts`.
- Existing `_make_run_results` helper in the test file must be extended to
  include `cat-file` call mocks for tests that exercise A/M/C paths.
