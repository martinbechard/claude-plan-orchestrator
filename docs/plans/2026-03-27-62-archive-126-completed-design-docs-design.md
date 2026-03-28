# Design: Archive ARCHIVE-classified Design Docs

## Overview

Move all design docs classified as ARCHIVE by the audit (docs/reports/design-doc-audit.md)
from docs/plans/ into docs/plans/archive/. This reduces noise in the active documentation
folder so only KEEP and UPDATE docs remain visible.

## Approach

1. Create docs/plans/archive/ directory
2. Parse docs/reports/design-doc-audit.md for all rows with classification ARCHIVE
3. Move each matching file from docs/plans/ to docs/plans/archive/
4. Verify docs/plans/ contains only KEEP, UPDATE, and new plan docs afterward

## Key Files

- **Source of truth:** docs/reports/design-doc-audit.md (audit classifications)
- **Source directory:** docs/plans/
- **Target directory:** docs/plans/archive/ (to be created)

## Design Decisions

- Use git mv (not filesystem mv) so git tracks the rename and history is preserved
- The audit found 132 ARCHIVE-classified docs; the backlog item says 126 because the
  count was taken before a later batch. Archive all ARCHIVE-classified docs regardless
  of the exact count
- Do not touch DELETE, KEEP, or UPDATE docs in this task (those are separate work items)
- A single task handles this since it is one atomic operation with no code changes
