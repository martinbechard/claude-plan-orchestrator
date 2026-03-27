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


## 5 Whys Analysis

Title: Queue Page for Workflow Visibility
Clarity: 4
5 Whys:
1. Why is a Queue page needed when the dashboard already shows a queue count metric?
   - Because displaying only a count provides no insight into what items are pending, making it impossible to assess queue health or identify problems.

2. Why is it important for users to see individual items rather than just a number?
   - Because the automated pipeline has limitations and gaps that require human oversight to detect slow-moving or stuck items.

3. Why would some items get stuck or move slowly without visibility?
   - Because pending items vary in type (defect/feature/analysis) and age, and these characteristics affect how urgently they need attention or what kind of intervention they require.

4. Why can't the system automatically manage priority and processing order?
   - Because different item types and states may have different SLAs, dependencies, or manual review requirements that the automation cannot assess alone.

5. Why do operators specifically need to see type and age together?
   - Because these attributes reveal operational patterns: type shows what work is accumulating, and age shows how long items are waiting, exposing bottlenecks and violations of implicit service levels.

Root Need: Operators require real-time visibility into pending work metadata (type and age) to detect processing bottlenecks, maintain pipeline health, and make informed decisions about priority and intervention.

Summary: The queue page enables operators to monitor pipeline queue health and identify work items requiring attention or prioritization.
