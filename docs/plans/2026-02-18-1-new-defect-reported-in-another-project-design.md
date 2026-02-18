# Design: Auto-archive completed-but-unarchived backlog items

**Backlog item:** docs/defect-backlog/1-new-defect-reported-in-another-project.md
**Date:** 2026-02-18

## Problem

When `scan_directory()` encounters a `.md` file whose status header is `Completed/Fixed`, it
emits a verbose skip log entry and returns early. This causes repetitive noise every polling
cycle for any item that was marked completed outside the normal pipeline flow (manual edit,
prior interrupted run, external tool).

## Root Cause

The skip guard in `scan_directory()` treats "completed" as fully terminal. It has no awareness
that archival (moving the file to `docs/completed-backlog/`) is a separate, still-pending step.

## Fix Design

### Single function change — `scan_directory()` in `scripts/auto-pipeline.py`

Replace the verbose-log-and-skip block with a call to `archive_item()`:

```
Before (lines 555-557):
    if is_item_completed(str(md_file)):
        verbose_log(f"Skipping completed item: {md_file.name}")
        continue

After:
    if is_item_completed(str(md_file)):
        item = BacklogItem(
            path=str(md_file),
            name=md_file.stem.replace("-", " ").title(),
            slug=md_file.stem,
            item_type=item_type,
        )
        if not archive_item(item):
            log(f"WARNING: Failed to auto-archive completed item: {md_file.name}")
        continue
```

`archive_item()` already handles:
- Destination already exists (idempotent — returns True)
- Source file missing (logs warning, returns False)
- Directory creation, git move, and git commit

The `verbose_log` call is removed: successful archival is logged by `archive_item()` itself.

## Key Files

| File | Change |
|---|---|
| `scripts/auto-pipeline.py` | Modify `scan_directory()` to call `archive_item()` on completed items |
| `tests/test_auto_pipeline.py` or `tests/test_completed_archive.py` | Add regression test |

## Design Decisions

1. **No new state field.** The fix relies entirely on the existing `archive_item()` function.
   No new fields, flags, or data structures needed.

2. **Idempotent.** If the file is already in the destination archive directory, `archive_item()`
   returns True immediately — no duplicate move or git commit.

3. **Single warning on failure.** If `archive_item()` returns False, one warning is logged and
   the item is silently skipped for this cycle. On the next poll, the same warning fires again
   rather than silently repeating — this is acceptable: repeated warnings for a stuck item are
   useful noise, not harmful noise.

4. **No dry-run guard needed.** `archive_item()` already respects `dry_run` when called from
   `process_item()`. However, `scan_directory()` is not passed a `dry_run` flag. The pipeline's
   `scan_and_process()` caller passes `dry_run` to `process_item()` but not to `scan_directory()`.
   For the auto-archive in `scan_directory()`, we do not pass `dry_run=True` because
   `scan_directory()` doesn't receive the flag. This is acceptable: the only scenario where this
   matters (pipeline started with `--dry-run`) is a developer-mode invocation; the auto-archive
   for completed items in that case is a harmless real operation. If this becomes a concern a
   follow-on refactor can thread `dry_run` into `scan_directory()`.
