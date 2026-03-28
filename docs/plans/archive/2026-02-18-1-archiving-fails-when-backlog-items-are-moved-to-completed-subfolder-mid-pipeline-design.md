# Design: Archiving Fails When Backlog Items Are Moved to completed/ Subfolder Mid-Pipeline

**Date:** 2026-02-18
**Defect:** docs/defect-backlog/1-archiving-fails-when-backlog-items-are-moved-to-completed-subfolder-mid-pipeline.md

## Problem Summary

`archive_item()` in `scripts/auto-pipeline.py` calls `shutil.move(item.path, dest)` using the
path captured at scan time. If a consumer project's orchestrator moves the file to a `completed/`
subfolder inside the backlog directory between scan time and archive time, the path is stale and
`shutil.move` raises `FileNotFoundError`.

## Architecture

### Root Cause

`BacklogItem.path` is set once in `scan_directory()` via `dir_path.glob("*.md")`. The auto-pipeline
assumes it has exclusive ownership of file locations between scan and archive. Consumer project
tooling can move a file to `<backlog_dir>/completed/<filename>` after scanning but before Phase 4.

### Fix: Resolve Actual Source Path Before Moving

Add a `_resolve_item_path()` helper that:
1. Returns `item.path` if the file exists there (happy path, no change to normal behavior).
2. If not, checks `<backlog_dir>/completed/<filename>` as a fallback.
3. Logs a notice if the fallback is used.
4. Returns `None` if neither location exists (caller logs a warning and returns False).

`archive_item()` calls this helper before `shutil.move()`. The git `add` uses the resolved path.

### Key Files

| File | Change |
|------|--------|
| `scripts/auto-pipeline.py` | Add `_resolve_item_path()` helper; update `archive_item()` to use it |
| `tests/test_auto_pipeline.py` | Add unit tests for `_resolve_item_path()` and updated `archive_item()` behavior |

### Design Decisions

- **No re-scan at archive time.** Re-scanning would be expensive and change the contract. A
  targeted fallback probe is minimal and reversible.
- **Only one fallback location.** The `completed/` subfolder is the only known convention used by
  consumer projects. Adding more would be speculative.
- **`archive_item()` signature unchanged.** The fix is entirely internal; no callers need to change.
- **Git `add` uses the resolved source path.** The resolved (actual) path must be staged, not the
  stale `item.path`, to avoid a git error when the paths differ.
- **`_resolve_item_path()` is a pure function** (no I/O side effects other than `os.path.exists`
  checks) to keep it easily testable.

### Resolved Path Logic

```
resolved = item.path
if not os.path.exists(resolved):
    backlog_dir = os.path.dirname(item.path)
    candidate = os.path.join(backlog_dir, "completed", os.path.basename(item.path))
    if os.path.exists(candidate):
        log(f"[ARCHIVE] Item moved to completed/ subfolder, using resolved path: {candidate}")
        resolved = candidate
    else:
        return None   # file not found anywhere
return resolved
```
