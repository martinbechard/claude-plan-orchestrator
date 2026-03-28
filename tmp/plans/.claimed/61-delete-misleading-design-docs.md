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
