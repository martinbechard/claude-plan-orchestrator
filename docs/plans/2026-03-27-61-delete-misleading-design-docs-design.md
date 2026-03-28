# Design: Delete Misleading Design Docs (Defect 61)

## Overview

Delete 10 design documents classified as DELETE by the design doc audit
(docs/reports/design-doc-audit.md). These documents contain misleading
references to the deleted plan-orchestrator.py script with specific line
numbers, which confuse agents that treat design docs as source of truth.

## Files to Delete

All files are in docs/plans/:

1. 2026-02-13-08-fix-in-progress-confusion-design.md (audit item 7, batch 1)
2. 2026-02-16-10-tiered-model-escalation-design.md (audit item 13, batch 1)
3. 2026-02-17-2-i-want-to-be-able-to-use-separate-slack-channels-depending-on-the-project-by-de-design.md (audit item 21, batch 1)
4. 2026-02-17-5-slack-bot-provides-truncated-unhelpful-responses-when-defect-submission-fails-validation-design.md (audit item 23, batch 1)
5. 2026-02-17-6-new-defect-when-a-defect-or-feature-is-received-the-agent-is-supposed-to-do-a-design.md (audit item 24, batch 1)
6. 2026-02-17-5-new-enhancement-when-accepting-the-feature-via-slack-you-need-to-acknowledge-w-design.md (audit item 25, batch 1)
7. 2026-02-17-7-pipeline-agent-commits-unrelated-working-tree-changes-design.md (audit item 30, batch 1)
8. 2026-02-18-1-add-configurable-conversation-history-for-follow-on-question-support-design.md (audit item 32, batch 1)
9. 2026-02-18-3-fix-git-stash-pop-failure-when-task-statusjson-has-uncommitted-changes-design.md (audit item 35, batch 1)
10. 2026-03-23-01-intake-single-digit-prefix-design.md (audit item 1, batch 3)

## Approach

Single task: delete all 10 files via git rm. This is a straightforward
file deletion with no code changes required.

## Acceptance Criteria

- All 10 DELETE-classified docs removed from docs/plans/
- No remaining DELETE-classified files in docs/plans/
