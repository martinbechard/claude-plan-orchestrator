# new defect reported in another project:

## Status: Open

## Priority: Medium

## Summary

`★ Insight ─────────────────────────────────────`
The 5 Whys technique works best when each successive "Why" answers the *previous* answer, not the original symptom. The chain should feel like peeling an onion — each layer reveals a deeper architectural or design gap.
`─────────────────────────────────────────────────`

**Title:** Auto-archive backlog items marked completed but still in the active backlog directory

**Classification:** defect - Completed items are never archived if the pipeline didn't perform the completion itself, causing repetitive skip log noise every polling cycle.

**5 Whys:**

1. **Why is "Skipping completed item: models-page-hardcoded-registry.md" logged every cycle?**
   Because `scan_directory()` finds the file in the active backlog directory each poll, `is_item_completed()` detects `## Status: Completed/Fixed` in its header, and the verbose log emits a skip message every time.

2. **Why is the file still in the active backlog directory if it's already completed?**
   Because archival (moving the file to `docs/completed-backlog/`) only happens at the end of `process_item()`, and `process_item()` was never invoked for this item — the skip logic short-circuits before processing begins.

3. **Why does the skip logic short-circuit instead of completing the pending archival?**
   Because the skip was designed purely as a safety guard to prevent re-processing finished work. It only checks the in-content status header and returns early — it has no awareness that archival is a separate, still-pending step.

4. **Why doesn't the skip logic know that archival is still pending?**
   Because the pipeline tracks completion via a single signal (the status header in the `.md` file) and treats "completed" as a terminal state. There is no distinction between "completed and archived" versus "completed but not yet archived."

5. **Why does the pipeline rely on a single completion signal with no separate archival state?**
   Because the original design assumed items always flow through the full linear lifecycle (scan → plan → orchestrate → verify → archive) in one uninterrupted pass. It never accounted for items that reach completed status outside that flow — via manual edits, prior interrupted runs, or external tools.

**Root Need:** The scan phase must detect completed-but-unarchived items and auto-archive them rather than silently skipping them indefinitely.

**Description:**
When `scan_directory()` encounters a `.md` file with `## Status: Completed/Fixed` still in the active backlog directory, it should auto-archive the file to `docs/completed-backlog/` instead of just logging a skip. If the archive attempt fails, log a single warning rather than repeating the skip message every cycle. This closes the gap where items completed outside the normal pipeline flow get stuck in a perpetual skip loop.

## Source

Created from Slack message by U0AEWQYSLF9 at 1771451756.307019.

## Verification Log

### Verification #1 - 2026-02-18 00:00

**Verdict: PASS**

**Checks performed:**
- [x] Build passes (syntax check: `py_compile` on both main scripts)
- [x] Unit tests pass (230/230 passed)
- [x] `scan_directory()` auto-archives completed-but-unarchived items instead of skipping
- [x] On archive failure, a single warning is logged rather than a repeated skip message
- [x] Incomplete items are still returned normally by `scan_directory()`

**Findings:**
- `py_compile` on `scripts/auto-pipeline.py` and `scripts/plan-orchestrator.py` both passed with no errors.
- All 230 unit tests passed in 2.75s.
- The fix is present in `scan_directory()` (scripts/auto-pipeline.py:555-564): when `is_item_completed()` returns True, the code now calls `archive_item(item)` and logs a warning if it fails, rather than logging a skip and returning early. The old repetitive skip-log path no longer exists.
- Three dedicated regression tests cover the defect exactly:
  - `test_scan_directory_auto_archives_completed_item` — PASSED: verifies `archive_item` is called and the item is excluded from the returned list.
  - `test_scan_directory_warns_on_archive_failure` — PASSED: verifies a WARNING is logged (not a skip) when archival fails.
  - `test_scan_directory_includes_incomplete_item` — PASSED: verifies non-completed items are still returned normally.
- The reported symptom ("Skipping completed item: ..." logged every polling cycle) is resolved: there is no skip-log code path remaining for completed items in `scan_directory()`.
