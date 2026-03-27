# Queue page: view and manage pending work items

## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


## Status: Open

## Priority: Medium

## Summary

The dashboard shows a queue count metric but there is no way to see what is
actually in the queue. A dedicated Queue page should list all pending work
items across the backlog directories with their type, slug, and age.

## Expected Behavior

- A new "Queue" nav link appears in the top navigation bar.
- The page lists all pending *.md files across BACKLOG_DIRS (defect, feature,
  analysis backlogs).
- Each row shows: type badge (defect/feature/analysis), slug/filename, and
  time since file was last modified (age).
- Rows are sorted by type then age (oldest first).
- The list auto-refreshes every 10-15 seconds (or is driven by a lightweight
  poll, not SSE, since queue changes are infrequent).
- Clicking a row opens the raw markdown content in a collapsible panel or
  modal so the user can read the item without leaving the page.

## Implementation Notes

- Backend: add GET /queue endpoint in a new routes/queue.py that reads
  BACKLOG_DIRS, globs *.md files, and returns a rendered template.
- The response includes each file's name, item_type (inferred from which
  BACKLOG_DIR it lives in), mtime, and raw markdown content.
- No write operations on this page — read-only view.
- The queue count in the dashboard summary bar can link to /queue.

## LangSmith Trace: 05260e5a-b276-4d81-b5e1-53c1a844f5b9
