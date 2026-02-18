# Prevent premature completed-subfolder moves and ensure archive runs exactly once

## Status: Open

## Priority: Medium

## Summary

`archive_item()` must locate the backlog file by probing its original path and, as a fallback, a `completed/` subfolder within the backlog directory, rather than assuming the file has not moved since scan. Additionally, the archive phase must be idempotent — if the file already exists at the destination, it should be treated as a success and not attempt a second move, preventing duplicate git commits or failures from concurrent or restarted pipeline runs.

## 5 Whys Analysis

  1. Why does archiving fail with "No such file or directory"? Because `archive_item()` uses `item.path` (set at scan time) but the file has already been moved to a `completed/` subfolder within the backlog directory.
  2. Why has the file been moved to a `completed/` subfolder? Because something in the pipeline (either the consumer orchestrator or auto-pipeline itself) is writing the file to that subfolder before Phase 4 runs, contrary to the expected single-move-to-archive contract.
  3. Why is something moving the file before Phase 4? Because there is no guard preventing the item from being relocated mid-pipeline, and the `completed/` subfolder convention used by some tooling is treated as a valid intermediate state rather than a terminal one.
  4. Why is there no such guard? Because the pipeline was designed assuming it has exclusive ownership of backlog file locations from scan through archive, so no single-owner invariant is enforced or checked before archiving.
  5. Why is the single-owner invariant not enforced? Because the archive logic does not assert that the file still exists at its original path, nor does it prevent `archive_item()` from being called more than once for the same item, leaving the pipeline vulnerable to both stale paths and double-archive attempts.

**Root Need:** The pipeline needs to enforce that each backlog item is moved to the archive exactly once, by resolving its current location at archive time and guarding against re-archival if it has already been moved.

## Source

Created from Slack message by U0AEWQYSLF9 at 1771420292.457819.

## Verification Log

### Verification #1 - 2026-02-18 09:30

**Verdict: PASS**

**Checks performed:**
- [x] Build passes (Python syntax check)
- [x] Unit tests pass (213/213)
- [x] `_resolve_item_path()` helper exists and falls back to `completed/` subfolder
- [x] `archive_item()` uses `_resolve_item_path()` instead of `item.path` directly
- [x] Idempotency guard: `archive_item()` checks `os.path.exists(dest)` before moving
- [x] WARNING log emitted when file found in `completed/` subfolder
- [x] `archive_item()` returns `False` (not an exception) when file not found at either location
- [x] `archive_item()` returns `True` and skips git when destination already exists

**Findings:**
- `python3 -c "import py_compile; ..."` completed with "Syntax OK" for both scripts
- `pytest tests/ -v` ran 213 tests, all passed in 2.45s
- `_resolve_item_path()` defined at auto-pipeline.py:1375 — checks `item.path` first, then `<backlog_dir>/completed/<filename>` as fallback, emits WARNING log on fallback match
- `archive_item()` at auto-pipeline.py:1394 has idempotency guard at line 1403 (`if os.path.exists(dest): return True` without calling git)
- 8 targeted tests all pass: `test_resolve_item_path_file_at_original_location`, `test_resolve_item_path_file_in_completed_subfolder`, `test_resolve_item_path_file_not_found`, `test_archive_item_succeeds_when_file_in_completed_subfolder`, `test_archive_item_returns_false_when_file_not_found`, `test_archive_item_idempotent_when_dest_exists`, `test_archive_item_idempotent_does_not_overwrite`, `test_resolve_item_path_warning_log_for_completed_subfolder`
- All three root behaviors from the defect summary are implemented and verified by dedicated regression tests
