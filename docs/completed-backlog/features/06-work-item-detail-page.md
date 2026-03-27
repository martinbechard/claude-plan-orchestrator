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




## 5 Whys Analysis

I see you want a focused analytical task—the 5 Whys analysis on this specific backlog item. That's different from the brainstorming design workflow. Let me apply that analysis directly:

---

**Title:** Understanding why a drill-down detail page is needed for work item visibility

**Clarity:** 4/5 (well-structured spec, but the underlying user need could be clearer)

**5 Whys:**

1. **Why does the dashboard need links to a detail page?**
   Because users viewing active workers or recent completions can only see a summary snapshot—they can't understand the full context of what a work item actually requires or how it's progressing without clicking through.

2. **Why can't users understand context from the dashboard summary?**
   Because the dashboard shows only immediate status (running/queued/completed) and cost roll-up, but doesn't expose the item's requirements (the markdown), its planned tasks, or its retry history—critical information for decision-making.

3. **Why is markdown content and plan status important to expose?**
   Because someone monitoring the pipeline needs to know: *What was the item supposed to do?* (requirements), *What steps are planned?* (tasks), and *How many times has this failed/succeeded?* (history)—without this, they can't troubleshoot blocks or validate completion.

4. **Why can't the team get this information from the source files directly?**
   Because the backlog files, plan YAMLs, and completion history are distributed across the filesystem and database—users would have to manually find and correlate multiple sources. The detail page centralizes this into one place per item.

5. **Why does centralizing information matter for this project's workflow?**
   Because the plan orchestrator runs autonomously, and when it stalls or makes unexpected decisions, a human needs to quickly investigate: *Is the item blocked?* *Was the plan wrong?* *Did a prior attempt fail?* The detail page eliminates context-switching and manual file hunting during incident triage.

---

**Root Need:** Enable rapid incident investigation and validation of orchestrator decisions by centralizing all metadata about a work item (requirements, plan, execution history) in one queryable location.

**Summary:** The detail page is infrastructure for observability—it turns the autonomous pipeline into something debuggable by making the full history and intent of each item visible on demand.
