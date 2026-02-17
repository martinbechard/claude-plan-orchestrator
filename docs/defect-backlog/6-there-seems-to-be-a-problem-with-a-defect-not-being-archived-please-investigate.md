# There seems to be a problem with a defect not being archived, please investigate

## Status: Open

## Priority: Medium

## Summary

Perfect! Now I have the complete picture. Let me perform the 5 Whys analysis:

---

**Title:** Auto-pipeline fails to archive defects when max verification cycles reached

**Classification:** defect - The system leaves orphaned backlog items in the defect-backlog when verification cycles are exhausted, causing confusion about item status and incomplete cleanup.

**5 Whys:**

1. **Why does defect #5 still exist in defect-backlog when its plan YAML was deleted?** Because when `MAX_VERIFICATION_CYCLES` (3) was reached in `process_item()`, the code cleaned up the plan YAML but did not archive the source markdown file to completed-backlog.

2. **Why doesn't `process_item()` archive the item when max cycles are reached?** Because the archiving logic at line 1650 only executes when `verified == True` (verification passed). When max cycles are exhausted (lines 1596-1604 and 1663-1671), the function returns `False` without calling `_archive_and_report()`.

3. **Why was the design structured to leave failed items in the queue rather than archive them?** The original intent (line 1669: "Defect stays in queue with accumulated verification findings") was likely to allow manual review/retry. However, the plan YAML cleanup (lines 1600-1603, 1666-1668) creates an inconsistent state - no plan exists, but the markdown remains in the active backlog.

4. **Why does this inconsistent state cause confusion?** Because tools that scan backlog directories count defect #5 as "pending," but the pipeline skips it on restart (no plan YAML, max cycles already hit). The item appears stuck in limbo - neither active nor archived.

5. **Why doesn't the fast-path check at line 1588-1590 handle this case?** Because `last_verification_passed()` only checks for "PASS" verdicts. Items with multiple "FAIL" verdicts don't get caught by the fast-path, forcing `process_item()` to check cycles on every restart and hit the early-return at lines 1596-1604, perpetually skipping the defect without resolution.

**Root Need:** The pipeline needs a consistent terminal state for defects that exceed max verification cycles - either archive them to a "failed" category or leave both the plan YAML and markdown intact for manual intervention, rather than creating a half-cleaned limbo state.

**Description:**

When a defect exceeds `MAX_VERIFICATION_CYCLES` (3 verification attempts), `auto-pipeline.py:process_item()` cleans up the plan YAML (lines 1600-1603, 1666-1668) but leaves the source markdown file in `defect-backlog/`. This creates an inconsistent state: the defect appears "pending" to backlog scanners but is perpetually skipped by the pipeline on restart because max cycles were already reached. The item becomes orphaned, causing confusion about its status and requiring manual cleanup. Either archive exhausted defects to a dedicated location (e.g., `completed-backlog/defects-failed/`) or preserve the plan YAML to signal the incomplete state.

## Source

Created from Slack message by U0AEWQYSLF9 at 1771351124.492069.

## Verification Log

### Verification #1 - 2026-02-17 13:12

**Verdict: PASS**

**Checks performed:**
- [x] Build passes
- [x] Unit tests pass (179/179 passed)
- [x] Defects are archived when max verification cycles are reached (early exit path, line 1616-1631)
- [x] Defects are archived when verification loop exhausts all cycles (end-of-loop path, line 1692-1705)
- [x] Status is updated to "Archived (verification failed)" before archiving
- [x] Plan YAML is cleaned up before archiving in both paths
- [x] No half-cleaned limbo state possible (archive always called after cleanup)

**Findings:**
- py_compile check passed for both scripts/auto-pipeline.py and scripts/plan-orchestrator.py (no syntax errors).
- All 179 unit tests pass, including the new test_process_item_archives_when_max_cycles_reached test in tests/test_completed_archive.py that directly validates the fix.
- Commit 5a41925 ("fix: archive defects when max verification cycles are exhausted") introduced the fix.
- Two code paths now call _archive_and_report() when max cycles are reached:
  1. Early exit (line 1616-1631): When remaining_cycles == 0 on entry, calls _mark_as_verification_exhausted() then _archive_and_report().
  2. Post-loop (line 1692-1705): After the for-loop exhausts cycles, calls _mark_as_verification_exhausted() then _archive_and_report().
- New helper _mark_as_verification_exhausted() (line 1549) replaces "## Status: Open" with "## Status: Archived (verification failed)" in the defect markdown before archiving.
- VERIFICATION_EXHAUSTED_STATUS constant defined at line 69.
- The reported symptom (orphaned defect in defect-backlog with deleted plan YAML) is resolved: both paths now archive the markdown file to completed-backlog before returning.
