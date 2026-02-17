# Design: Archive defects when max verification cycles are exhausted

## Problem

When a defect exceeds MAX_VERIFICATION_CYCLES (3), process_item() in auto-pipeline.py
cleans up the plan YAML but leaves the source markdown in defect-backlog/. This creates
an inconsistent "limbo" state:

- The item appears active to scan_all_backlogs()
- The pipeline perpetually skips it (no plan YAML, max cycles hit)
- The item is never archived to completed-backlog/

## Root Cause

Two code paths in process_item() handle max-cycle exhaustion:

1. Lines 1596-1604: Early check when remaining_cycles == 0 (on restart)
2. Lines 1663-1671: After the for-loop completes (all cycles used in this session)

Both paths clean up the plan YAML and return False without calling _archive_and_report().
The item stays in defect-backlog/ indefinitely.

## Solution

Archive exhausted defects to completed-backlog/defects/ just like successfully verified
defects, but append a status marker to the markdown file first so it is clear the item
failed verification (as opposed to passing). This provides a clean terminal state.

### Changes

#### 1. scripts/auto-pipeline.py

Modify both max-cycle-exhaustion paths to call _archive_and_report() instead of just
cleaning up the plan YAML and returning False.

Before archiving, append a "## Status: Archived (verification failed)" marker to the
defect markdown so reviewers can distinguish successful fixes from exhausted ones.

Specifically:
- At lines 1596-1604 (remaining_cycles == 0 on restart): after cleaning plan YAML,
  call _archive_and_report(item, slack, item_start, dry_run)
- At lines 1665-1671 (loop exhausted): after cleaning plan YAML,
  call _archive_and_report(item, slack, item_start, dry_run)
- Add a helper function _mark_as_verification_exhausted(item_path) that updates the
  Status line from "Open" to "Archived (verification failed)" in the markdown
- Call _mark_as_verification_exhausted() before _archive_and_report() in both paths
- Send a distinct Slack notification indicating the defect was archived due to
  exhausted verification cycles (warning level)

#### 2. tests/test_completed_archive.py

Add unit tests:
- test_process_item_archives_on_max_cycles_exhausted: verify that when remaining
  cycles are 0, the item is archived (not left in limbo)
- test_mark_as_verification_exhausted: verify the status line is updated in the
  markdown file
- test_process_item_archives_after_loop_exhaustion: verify that when the for-loop
  completes without a PASS, the item is archived

## Design Decisions

1. Archive to the same completed-backlog/defects/ directory rather than a separate
   "failed" directory. This keeps the archive scanning simple. The status marker in
   the file content distinguishes pass/fail.

2. Update the Status line in the markdown rather than adding a new section. The
   Status field already exists ("## Status: Open") and is the natural place to
   record the terminal state.

3. Return True from process_item() after successful archiving even for exhausted
   items. The item has been processed to completion (its terminal state). Returning
   False would add the item to failed_items, but since the file has been moved out
   of defect-backlog/, scan_all_backlogs() would not pick it up again anyway.
   However, returning False is safer to signal that the defect was not successfully
   fixed - the pipeline just gave up. Keep returning False but ensure the item does
   not remain in the active backlog.

## Key Files

- scripts/auto-pipeline.py (primary fix)
- tests/test_completed_archive.py (regression tests)
- docs/defect-backlog/6-*.md (the specific orphaned defect - will be archived by fix)
