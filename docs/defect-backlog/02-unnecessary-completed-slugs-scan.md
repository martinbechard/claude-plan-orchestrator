# Unnecessary completed_slugs() Scan on Every Pipeline Cycle

## Status: Open

## Priority: Low

## Summary

The auto-pipeline calls completed_slugs() on every scan cycle to filter out
completed items from the backlog scan results. Since feature 09 moved all
completed items to a separate directory (docs/completed-backlog/), they no
longer appear in the backlog directories (docs/feature-backlog/ and
docs/defect-backlog/). The filter is dead logic that adds filesystem I/O
and noisy verbose logging for no purpose.

## Root Cause

Before feature 09, completed items lived in subdirectories inside the backlog
folders (e.g., docs/feature-backlog/completed/). The completed_slugs() function
scanned those subdirectories to build a set of slugs to exclude from processing.
After feature 09, completed items moved to docs/completed-backlog/defects/ and
docs/completed-backlog/features/. The scan directories no longer contain
completed items, making the filter redundant.

The completed_slugs() function itself was updated (feature 09, task 1.1) to
read from the new locations, but the callers were never removed because the
function still "works" - it just does unnecessary work.

## Observed Behavior

Every 60 seconds in verbose mode, the pipeline logs the full set of completed
slugs, producing noisy output like:

    [VERBOSE] Completed slugs: {'14-slack-app-migration', '02-agent-definition-framework', ...}

This set grows with every completed item and provides no value.

## Proposed Fix

1. Remove the completed_slugs() call from main_loop in auto-pipeline.py
2. Remove the filtering logic that excludes completed slugs from scan results
3. Evaluate whether completed_slugs() itself is still needed anywhere. If not,
   remove the function entirely. If the orchestrator still uses it, leave it
   but remove it from the pipeline's hot path.
4. Remove the verbose log line that prints the completed set.

## Files Affected

| File | Change |
|------|--------|
| scripts/auto-pipeline.py | Remove completed_slugs() call and filtering in main_loop |

## Verification Log

### Verification #1 - 2026-02-16 22:45

**Verdict: PASS**

**Checks performed:**
- [x] Build passes (py_compile on auto-pipeline.py and plan-orchestrator.py - no errors)
- [x] Unit tests pass (114 passed, 5 failed - failures are in test_slack_notifier.py unrelated to this defect; all 4 test_completed_archive.py tests pass)
- [x] completed_slugs() is no longer called eagerly on every scan cycle in main_loop
- [x] The verbose log line printing "Completed slugs: {...}" is removed
- [x] completed_slugs() function retained for dependency resolution (still needed)
- [x] Lazy evaluation implemented - only called when items have dependencies

**Findings:**

1. **py_compile check**: Both scripts/auto-pipeline.py and scripts/plan-orchestrator.py compile without errors.

2. **Unit tests**: 114 passed, 5 failed. The 5 failures are all in tests/test_slack_notifier.py (AttributeError: _load_last_read, _save_last_read methods missing) - these are pre-existing failures unrelated to this defect. All 4 tests in tests/test_completed_archive.py pass.

3. **Symptom gone - no eager call in main_loop**: grep for completed_slugs() shows only two occurrences in auto-pipeline.py: the function definition (line 424) and one call inside scan_all_backlogs() (line 461). There is NO direct call in main_loop. The old pattern of calling completed_slugs() on every 60-second cycle is eliminated.

4. **Symptom gone - no noisy verbose log**: grep for "Completed slugs" in auto-pipeline.py returns zero matches. The verbose log line that printed the full set every cycle has been removed.

5. **Lazy evaluation**: scan_all_backlogs() (lines 438-469) now uses lazy evaluation. A local variable done is initialized to None (line 449). completed_slugs() is only called if an item has dependencies AND done is still None (lines 460-461). If no backlog items have dependencies, completed_slugs() is never called - zero filesystem I/O for the common case.

6. **Function retained**: completed_slugs() is still defined (line 424) because it is needed for dependency resolution within scan_all_backlogs(). This matches proposed fix item 3.
