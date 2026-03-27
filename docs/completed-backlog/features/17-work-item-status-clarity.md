# Work item detail page: show clear real-time status of what is happening

## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


## Status: Open

## Priority: High

## Summary

When viewing a work item on /item/<slug>, there is no indication of what
the pipeline is currently doing with it. The page shows "No requirements
document found" and "No plan found" even when a worker is actively
processing the item. The user cannot tell whether the item is queued,
being designed, being planned, being executed, being validated, or stuck.

## Expected Behavior

The work item detail page should show a clear status section at the top
that answers "what is happening with this item right now?" including:

### Current pipeline stage
- Queued (in backlog, not claimed)
- Claimed (in .claimed/, worker assigned)
- Designing (design doc being created, no plan yet)
- Planning (design doc exists, plan YAML being created)
- Executing (plan exists, tasks being run — show which task)
- Validating (validator running)
- Completed (archived)
- Stuck / warn (multiple failed attempts)

### How to determine stage
- Check if the .md is in a backlog dir → Queued
- Check if the .md is in .claimed/ → Claimed
- Check if a design doc exists in docs/plans/ → Designing or later
- Check if a .yaml plan exists in .claude/plans/ → Planning or later
- Check plan YAML task statuses → Executing (show current task)
- Check active_workers in DashboardState for this slug → show PID and
  elapsed time
- Check completions table for this slug → show history

### Active worker indicator
If the item is currently being processed by a worker, show:
- "Currently running" badge with PID and elapsed time
- Link to trace if run_id is available
- Which pipeline stage the worker is in (design/plan/execute/validate)

### Progress through plan tasks
If a plan exists, show a progress indicator (e.g. "3 of 7 tasks complete")
alongside the task list, not just the raw task checkboxes.

## Implementation Notes

- The /item/<slug> route already loads completions and traces. Add checks
  for: file existence in backlog dirs / .claimed/, design doc in docs/plans/,
  plan YAML in .claude/plans/, active worker in DashboardState.
- Use the existing DashboardState.active_workers to check if a worker is
  running for this slug.
- The stage determination is a simple waterfall of file existence checks.




## 5 Whys Analysis

Title: Pipeline progress visibility drives user confidence in asynchronous processing

Clarity: 4/5

5 Whys:

1. **Why can't users see what the pipeline is currently doing?**
   Because the work item detail page only displays completed artifacts (traces, completion history) and static checks (document existence), not live pipeline state like active workers, current task progress, or intermediate processing stages.

2. **Why wasn't real-time pipeline state integrated into the page?**
   Because the pipeline's current state is distributed across multiple locations (backlog directories, .claimed/, docs/plans/, .claude/plans/, DashboardState), and there's no unified interface to query what stage an item is actually in at any moment.

3. **Why is this distribution of state a problem for users?**
   Because when users see "No plan found" they have no way to know if it's because the item is queued, being claimed, actively being designed right now, or genuinely stuck—all these states would show the same missing-document message.

4. **Why does this ambiguity matter if users just wait?**
   Because the pipeline's asynchronous processing means hours can pass between state changes with no feedback, and without intermediate progress indicators, users lose confidence and assume the system has failed or forgotten their item.

5. **Why does absence of intermediate feedback erode confidence?**
   Because humans distinguish "slow but working" from "broken" by seeing evidence of progress; silence in an asynchronous system reads as abandonment, leading users to take unintended action (re-submissions, escalations, giving up).

Root Need: **Establish user confidence in asynchronous pipeline work by providing real-time stage visibility**, so users can distinguish normal multi-stage processing from genuine blockages without constant manual investigation.

Summary: Users need live progress visibility at each pipeline stage to maintain trust that submitted items are being processed and to identify when intervention is actually needed.
