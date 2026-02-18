# Design: Prevent Premature completed/ Subfolder Moves and Ensure Archive Runs Exactly Once

## Date: 2026-02-18

## Defect Reference

docs/defect-backlog/2-prevent-premature-completed-subfolder-moves-and-ensure-archive-runs-exactly-once.md

## Problem Statement

Two related deficiencies in the archive phase of `auto-pipeline.py`:

1. **No premature-move guard**: External tooling or the pipeline itself can move a backlog file into
   a `completed/` subfolder within the backlog directory before Phase 4 (archive) runs. There is no
   assertion or guard that flags this as unexpected. Defect 1 added a fallback to _find_ the file
   there, but nothing prevents or detects the premature relocation.

2. **Non-idempotent archive**: If `archive_item()` is called twice for the same item (e.g., pipeline
   restart after a crash mid-commit, or concurrent runs), `shutil.move()` will either overwrite the
   destination silently or raise an `OSError` because the destination already exists. The function
   should treat an already-present destination as success and skip the move + git commit.

## Architecture Overview

All changes are confined to `scripts/auto-pipeline.py`.

### Change 1 — Idempotent archive in `archive_item()`

Add a destination-exists check before calling `shutil.move()`. If the file is already at `dest`,
log an info message and return `True` without a git commit (the file was already committed in the
first archive attempt).

```
archive_item():
    dest = COMPLETED_DIRS[item.item_type] / basename
    if dry_run: return True
    if os.path.exists(dest):          # <- NEW: idempotency guard
        log("[ARCHIVE] Already archived, skipping: dest")
        return True
    source = _resolve_item_path(item)
    if source is None: return False   # existing guard
    shutil.move(source, dest)
    git add + commit
    return True
```

### Change 2 — Premature-move detection in `_resolve_item_path()`

Upgrade the fallback branch from a silent log to a `WARNING`-level log so operators can identify
when external tooling is relocating files mid-pipeline. The function behavior is unchanged; only
the log severity changes to make the condition more visible in monitoring.

```
_resolve_item_path():
    if os.path.exists(item.path): return item.path
    candidate = completed/<filename>
    if os.path.exists(candidate):
        log("WARNING: [ARCHIVE] Item relocated to completed/ subfolder — unexpected mid-pipeline move: candidate")
        return candidate
    return None
```

## Key Files

| File | Change |
|------|--------|
| `scripts/auto-pipeline.py` | Add idempotency guard in `archive_item()`; upgrade log level in `_resolve_item_path()` |
| `tests/test_auto_pipeline.py` | Add regression tests for idempotency guard and warning log |

## Design Decisions

- **Idempotency before source resolution**: The destination check happens _before_
  `_resolve_item_path()` so that a double-archive attempt short-circuits immediately, even if the
  source file no longer exists (it was already moved in the first run).

- **No new git commit on re-archive**: Committing an already-committed move would produce a
  no-op or confusing git history. The guard returns `True` without committing.

- **Warning not error for premature move**: The premature-move case is operationally recoverable
  (the file is found and archived correctly), so it warrants a WARNING rather than a failure.
  This surfaces the unexpected relocation for operator investigation without breaking the pipeline.

- **Scope limited to two targeted changes**: No refactoring of surrounding logic. The two changes
  are the minimum needed to satisfy the root need stated in the defect.
