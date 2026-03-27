# Work item page: show last run trace and average velocity

## Summary

Two missing pieces of information on the /item/<slug> detail page:

1. The last run (trace) associated with the item should be prominently
   linked so the user can quickly drill into the most recent execution.
   Currently traces are listed at the bottom but the most recent one
   should be surfaced near the status.

2. The average velocity (tokens per minute) during execution should be
   displayed as a badge/tag next to the pipeline stage status. This
   value should come from the completions table or the active worker's
   current velocity. This same value drives the colour of the dashboard
   timeline bars in velocity mode.

## Acceptance Criteria

- Does the item detail page show a link to the most recent trace near
  the top (not just in the traces table at the bottom)?
  YES = pass, NO = fail
- Does the item detail page show average tokens/min as a tag next to
  the pipeline stage badge? YES = pass, NO = fail
- Is the velocity value consistent with what the dashboard timeline
  shows for the same item? YES = pass, NO = fail
