# Archiving fails when backlog items are moved to completed/ subfolder mid-pipeline

## Status: Open

## Priority: Medium

## Summary

When a consumer project's orchestrator moves a completed backlog item into a `completed/` subfolder mid-pipeline, the auto-pipeline's Phase 4 fails because `item.path` still points to the original root-level location. The fix should update `archive_item()` to probe the `completed/` subfolder as a fallback when the primary path does not exist, resolving the stale-path assumption without requiring changes to the consumer project's workflow.

## 5 Whys Analysis

  1. Why does archiving fail with "No such file or directory"? Because `archive_item()` calls `shutil.move(item.path, dest)` using a path that no longer exists at the expected location.
  2. Why does the file no longer exist at `item.path`? Because the consumer project's orchestrator moved the completed file into a `completed/` subfolder inside the backlog directory before the auto-pipeline's Phase 4 ran.
  3. Why does the auto-pipeline use a stale path? Because `BacklogItem.path` is set once at scan time via `glob("*.md")` on the backlog root and is never refreshed before archiving.
  4. Why is the path never refreshed? Because the auto-pipeline assumes it has exclusive ownership of backlog file locations and does not anticipate that the consumer project's tooling will relocate files mid-pipeline.
  5. Why does no contract or guard exist to detect this? Because the auto-pipeline was designed for a single-owner model where no external process touches backlog files between scan and archive, so the `completed/` subfolder convention used by consumer projects was never anticipated or handled.

**Root Need:** The auto-pipeline must locate a backlog item's file at archive time by searching for it at its original path and also under any `completed/` subfolder, rather than assuming the file has not moved since scan time.

## Source

Created from Slack message by U0AEWQYSLF9 at 1771420141.082789.

## Verification Log

### Verification #1 - 2026-02-18 08:24

**Verdict: PASS**

**Checks performed:**
- [x] Build passes (Python syntax check)
- [x] Unit tests pass (210 tests)
- [x] `_resolve_item_path()` helper is present in `scripts/auto-pipeline.py`
- [x] `archive_item()` calls `_resolve_item_path()` before `shutil.move()`
- [x] Case 1: file found at original path (returns `item.path`)
- [x] Case 2: file found in `completed/` subfolder fallback (returns relocated path)
- [x] Case 3: file not found anywhere (returns `None`, `archive_item` returns `False`)
- [x] 6 dedicated unit tests for `_resolve_item_path` and `archive_item` fallback all pass

**Findings:**

- `python3 -c "import py_compile; py_compile.compile(...)"` → `syntax OK` for both `auto-pipeline.py` and `plan-orchestrator.py`
- `~/.pyenv/versions/3.11.*/bin/python -m pytest tests/ -v` → `210 passed in 2.39s`
- `_resolve_item_path()` is defined at line 1375 of `scripts/auto-pipeline.py`; `archive_item()` is at line 1394 and correctly delegates path resolution to `_resolve_item_path()` before calling `shutil.move()`
- Smoke test output confirms all three resolution cases work correctly:
  - Case 1 (file at original path): PASS
  - Case 2 (file relocated to `completed/` subfolder): PASS — log line `[ARCHIVE] Item relocated to completed/ subfolder, using: ...` was emitted as expected
  - Case 3 (file not found anywhere): PASS — returned `None`
- All 6 unit tests (`test_resolve_item_path_file_at_original_location`, `test_resolve_item_path_file_in_completed_subfolder`, `test_resolve_item_path_file_not_found`, `test_archive_item_succeeds_when_file_in_completed_subfolder`, `test_archive_item_returns_false_when_file_not_found`, `test_archive_item_dry_run_does_not_require_file`) passed individually.
- The original symptom (archiving fails with `FileNotFoundError` when the file has been moved to a `completed/` subfolder mid-pipeline) is resolved: `archive_item()` now successfully locates and moves the file from the fallback location.
