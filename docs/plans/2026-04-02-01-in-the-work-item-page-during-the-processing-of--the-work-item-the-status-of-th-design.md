# Design: Phase Status Badge Not Displaying Properly

Source: tmp/plans/.claimed/01-in-the-work-item-page-during-the-processing-of--the-work-item-the-status-of-th.md
Requirements: docs/plans/2026-04-02-01-in-the-work-item-page-during-the-processing-of--the-work-item-the-status-of-th-requirements.md

## Architecture Overview

The work item page renders a stage badge in the item header (line 1181 of item.html).
The badge is rendered both server-side (Jinja template) and client-side (JavaScript
stageBadgeHtml function for dynamic refresh). Both paths contain the same bug:

**Current behavior**: When an active worker has a current_task, the badge text shows the
task name (e.g., "#0.1 Systems design: content-type rendering architecture") instead of
the pipeline phase name. When executing/validating with no current_task, it shows
"intake / planning" -- a hardcoded fallback that is also incorrect.

**Expected behavior**: The badge should always display the pipeline phase name
(e.g., "executing", "validating", "planning") as its primary text. The current task
information can optionally be shown elsewhere (e.g., the active worker banner).

## Key Files to Modify

- langgraph_pipeline/web/templates/item.html -- Jinja template (badge rendering + JS function)

No new files needed. No backend changes needed -- pipeline_stage is already correctly
computed by _derive_pipeline_stage() and passed to the template.

## Design Decisions

### D1: Fix Jinja template badge to show pipeline_stage instead of current_task
Addresses: P1, P2
Satisfies: AC1, AC2, AC3, AC5
Approach: In the Jinja template (lines 1181-1196), replace the active_worker.current_task
branch that renders the task name with a branch that always renders pipeline_stage as the
badge text. The badge CSS class already uses pipeline_stage correctly (status-{{ pipeline_stage }}).
Remove the "intake / planning" hardcoded fallback -- replace with the actual pipeline_stage value.
Files: langgraph_pipeline/web/templates/item.html (Jinja section)

### D2: Fix JavaScript stageBadgeHtml to show pipeline stage instead of current_task
Addresses: P1, P2
Satisfies: AC1, AC2, AC3, AC4, AC5, AC6
Approach: In the stageBadgeHtml JavaScript function (lines 1835-1848), remove the
worker.current_task branch that uses the task name as badge text. Always render the
stage parameter as the badge label. Remove the "intake / planning" hardcoded fallback.
This ensures the badge stays correct across dynamic refreshes as the pipeline progresses.
Files: langgraph_pipeline/web/templates/item.html (JavaScript section)

### D3: Preserve current_task info in the active worker banner
Addresses: P2
Satisfies: AC5
Approach: The active worker banner (workerBannerHtml function) already shows current task
information. Verify it continues to work correctly after the badge fix. The current_task
data still flows from the backend -- it simply no longer overrides the phase badge. No
change expected here unless the banner also needs updating.
Files: langgraph_pipeline/web/templates/item.html (verify only)

## Design -> AC Traceability Grid

| AC | Design Decision(s) | Approach |
|---|---|---|
| AC1 (phase badge displayed during processing) | D1, D2 | Badge always renders pipeline_stage as text in both Jinja and JS paths |
| AC2 (badge visually distinct from plan items) | D1 | Badge uses status-{stage} CSS class, not plan item content |
| AC3 (badge label matches current phase) | D1, D2 | Badge text is the pipeline_stage value computed by _derive_pipeline_stage() |
| AC4 (phase updates on transition) | D2 | JS dynamic refresh calls stageBadgeHtml with fresh pipeline_stage from /dynamic endpoint |
| AC5 (first plan item not rendered as status) | D1, D2, D3 | current_task removed from badge rendering; kept only in worker banner |
| AC6 (status reflects current phase, not stale) | D2 | Dynamic refresh updates badge every poll interval with current pipeline_stage |
