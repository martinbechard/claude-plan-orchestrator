# Intake creates files with single-digit prefix that scanner ignores

## Status: Open

## Priority: High

## Summary

The Slack intake creates backlog files with a single-digit prefix (1-slug.md, 2-slug.md) but scan_backlog in langgraph_pipeline/pipeline/nodes/scan.py uses BACKLOG_SLUG_PATTERN = re.compile(r"^\d{2,}-[\w-]+$") which requires 2+ digits. This means all intake-created files are silently ignored by the scanner.

## Expected Behavior

Intake-created files should use zero-padded two-digit prefixes (01-slug.md, 02-slug.md) so the scanner picks them up.

## Actual Behavior

Files are created as 1-slug.md, 2-slug.md, 3-slug.md and the scanner skips them because the slug doesn't match \d{2,}.

## Fix Required

Either:
- (a) Change the intake numbering to use %02d format (preferred)
- (b) Relax BACKLOG_SLUG_PATTERN to accept single digits: r"^\d+-[\w-]+"

Also: the RAG deduplication did not catch that two nearly identical defects were filed within 2 minutes of each other about the same issue.

## Verification

1. Submit a defect via Slack
2. Check that the created file has a 2-digit prefix (01-, 02-, etc.)
3. Verify the scanner picks it up on the next scan cycle
