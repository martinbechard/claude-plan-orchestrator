# Work item detail page with drill-down from dashboard

## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


## Status: Open

## Priority: Medium

## Summary

Add a work item detail page that shows full information about a specific work
item: its markdown content (requirements/description), associated plan YAML
(tasks and status), recent completions for that slug, and linked traces. The
dashboard active worker cards and recent completion rows should link to this
page by slug.

## Expected Behavior

### Navigation
- Every place a work item slug/title is displayed becomes a clickable link:
  - Active Worker cards (slug in header)
  - Recent Completions rows (slug column)
  - Queue page rows (once built)
- Links go to /item/<slug>

### Work Item Detail Page (/item/<slug>)
- Header card: slug, item type badge, current status (queued / running /
  completed), total cost across all completions for this slug.
- Requirements section: rendered markdown of the source .md file from the
  backlog or completed-backlog directory.
- Plan section: if a .claude/plans/<slug>.yaml exists, show it as a task
  list with completion status per task (checked/unchecked). If no plan,
  show a "No plan yet" placeholder.
- Completion history: table of all completions for this slug from the
  completions DB (outcome, cost, duration, finished_at) — there may be
  multiple if the item was retried.
- Traces: list of linked root traces (once trace slug association is fixed
  by defect 02); links to /proxy?trace_id=<run_id>.

### UI Design
- Use the frontend-design skill when implementing to ensure a polished,
  professional layout — not a plain dump of text.
- Suggested layout: two-column on wide screens (requirements left,
  plan + history right), single column on narrow screens.
- Use clear section separators, task checkboxes for plan items, and
  outcome color coding for completion history rows.

## Implementation Notes

- Backend: new GET /item/{slug} endpoint in routes/item.py.
- Find the source .md file by scanning BACKLOG_DIRS and completed-backlog.
- Find the plan YAML at .claude/plans/{slug}.yaml (or glob for partial match).
- Query completions table: SELECT * FROM completions WHERE slug = ? ORDER BY
  finished_at DESC.
- Query traces: SELECT run_id, name, created_at FROM traces WHERE
  parent_run_id IS NULL AND name LIKE ? (or by metadata once defect 02 fixed).

## Dependencies

- Defect 06 (drill-down links from dashboard) shares the same slug→URL pattern.
- Defect 02 (traces named LangGraph) blocks the traces section being useful,
  but the page should be built regardless with a placeholder.

## LangSmith Trace: 334ee53b-cee4-4c0f-a5da-bad358e8c676
