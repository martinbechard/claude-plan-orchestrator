# Audit design docs in docs/plans/ for validity and accuracy

## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


## Status: Open

## Priority: Medium

## Summary

There are 142 design documents in docs/plans/. Many reference the old
plan-orchestrator.py (now deleted) or contain directives that are now wrong
(e.g. the tilde cost prefix convention that was explicitly removed). Pipeline
agents read these docs during plan creation and may follow outdated
instructions.

## Analysis Instructions

1. Read each design document in docs/plans/.
2. For each document, determine:
   - Does it reference scripts/plan-orchestrator.py or the old auto-pipeline
     code that no longer exists? If so, flag for update or deletion.
   - Does it contain directives or conventions that conflict with current
     CLAUDE.md, MEMORY.md, or the actual codebase? If so, flag for update.
   - Is the corresponding backlog item completed? If so, does the design doc
     still provide value as architecture reference, or is it purely
     implementation detail that is now in the code?
   - Does the document reference file paths, function names, or modules that
     no longer exist?
3. Classify each document as one of:
   - KEEP: still accurate and useful as architecture reference
   - UPDATE: useful but contains outdated references that need correction
   - ARCHIVE: completed work, no longer useful, can be moved to an archive
   - DELETE: contains harmful outdated directives that could mislead agents
4. Produce a summary report listing each document with its classification
   and the specific issues found.
5. For each document classified as UPDATE, create a separate analysis task
   to review and update that specific document.

## Output

Post a summary to Slack and save the classification report to
docs/reports/design-doc-audit.md.
