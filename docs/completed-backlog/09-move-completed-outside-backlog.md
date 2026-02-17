# Move Completed Items Outside Backlog Directories

## Status: Open

## Priority: Low

## Summary

The auto-pipeline stores completed backlog items in completed/ subdirectories inside the
defect and feature backlog folders (docs/defect-backlog/completed/, docs/feature-backlog/completed/).
On every scan cycle, the pipeline lists and reads all completed files to build a set of
completed slugs for dependency resolution. As completed items accumulate, this becomes
wasteful - the pipeline logs dozens of "Skipping completed item" lines and builds a large
set that grows monotonically.

## Proposed Fix

Move the completed directories to a separate top-level location outside the backlog folders,
for example docs/completed-backlog/defects/ and docs/completed-backlog/features/.

This way:
- scan_directory() only sees open items (no completed/ subdirectory to skip)
- completed_slugs() reads from the dedicated archive location
- The filesystem watcher does not receive events for completed item moves
- Backlog folders stay clean and only contain actionable items

## Files Affected

| File | Change |
|------|--------|
| scripts/auto-pipeline.py | Update COMPLETED_SUBDIR paths, scan_directory, completed_slugs, archive logic |

## Dependencies

None
