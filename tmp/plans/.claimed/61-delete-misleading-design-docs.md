# Delete 10 design docs classified as DELETE by the audit

## Summary

The design doc audit classified 10 documents as DELETE — they contain
misleading references to deleted scripts with specific line numbers that
would confuse agents. Delete them.

## Files to delete

See docs/reports/design-doc-audit.md for the full list. Documents
classified as DELETE are items 7, 13, 21, 23, 24, 25, 30, 32, 35
from the audit.

## Acceptance Criteria

- Are all 10 DELETE-classified docs removed from docs/plans/?
  YES = pass, NO = fail
- Do the remaining docs in docs/plans/ contain zero DELETE-classified files?
  YES = pass, NO = fail

## LangSmith Trace: e9ff9687-fd04-44f0-9d42-0b492d6f42bd


## 5 Whys Analysis

**Title:** Delete design docs containing stale script references to prevent agent confusion

**Clarity:** 4/5  
Clear deletion task with specific file references and acceptance criteria, though depends on cross-referencing external audit report.

**5 Whys:**

1. **Why must these 10 design docs be deleted?**
   - They contain misleading references to deleted scripts with specific line numbers, which cause agents to become confused or fail when trying to locate non-existent code.

2. **Why would stale script references confuse agents?**
   - Agents treat design documentation as a source of truth for understanding the codebase structure. When docs point to deleted code, agents cannot verify documented processes or follow instructions accurately.

3. **Why do design docs contain references to scripts that no longer exist?**
   - The scripts were deleted or refactored at some point, but the design documentation was not updated to reflect those changes—documentation drifted out of sync with the codebase.

4. **Why wasn't the documentation updated when the scripts were deleted?**
   - There is no enforced process to keep documentation synchronized with code changes. Developers can delete/modify code without automatically updating all references in design docs.

5. **Why is there no process to keep documentation in sync with code changes?**
   - Documentation maintenance was never formalized as part of the development workflow, and there are no automated checks, reviews, or responsibility assignments to catch stale documentation.

**Root Need:** Establish a synchronization mechanism (process or automation) to ensure design documentation remains accurate with the current codebase state so agents and developers can rely on it as a trustworthy reference.

**Summary:** Remove misleading stale documentation immediately to unblock agent operations, while uncovering the need for an ongoing docs-code sync process to prevent recurrence.
