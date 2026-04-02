# Design: Phase Status Badge on Work Item Page

Source: tmp/plans/.claimed/01-in-the-work-item-page-during-the-processing-of--the-work-item-the-status-of-th.md
Requirements: docs/plans/2026-04-02-01-in-the-work-item-page-during-the-processing-of--the-work-item-the-status-of-th-requirements.md

## Architecture Overview

The work item page header displays a status badge (item.html:1181-1196, JS
stageBadgeHtml at line 1835). Currently it renders the active worker's current_task
name (e.g., "#0.1 Systems design: ...") or a hardcoded "intake / planning" fallback
instead of the pipeline phase. The fix requires:

1. A backend mapping from pipeline_stage to human-readable phase labels
2. Exposing that label in both the Jinja2 template context and /dynamic JSON
3. Updating the template and JS to render the phase label as the primary badge
4. CSS styling to make the phase badge visually distinct from plan items

### Bug Analysis

stageBadgeHtml() (item.html:1835) does:
- Worker has current_task: renders task name as badge text (BUG: shows plan item)
- Stage executing/validating with no task: renders "intake / planning" (BUG: wrong label)
- Otherwise: renders raw pipeline_stage string (e.g., "executing" not "Execution")

The root cause is that the badge was designed to show task-level detail instead of
phase-level status. The pipeline_stage value IS the correct phase indicator, but it
needs translation to user-facing labels matching STAGE_ORDER (item.py:86).

### Key Files

- langgraph_pipeline/web/routes/item.py -- Add phase_label mapping, expose in
  template context and /dynamic JSON endpoint
- langgraph_pipeline/web/templates/item.html -- Fix Jinja2 badge, fix JS
  stageBadgeHtml(), add phase badge CSS

## Design Decisions

### D1: Pipeline stage to phase label mapping
Addresses: P3, FR2
Satisfies: AC5
Approach: Add a PIPELINE_STAGE_TO_PHASE_LABEL dict in item.py that maps each
pipeline_stage string to a user-facing phase label. This uses STAGE_ORDER as the
source of truth for labels. The mapping is:
- "queued" -> "Queued"
- "claimed" -> "Intake"
- "designing" -> "Requirements"
- "planning" -> "Planning"
- "executing" -> "Execution"
- "validating" -> "Verification"
- "completed" -> "Completed"
- "stuck" -> "Stuck"
- "unknown" -> "Unknown"
Add a helper function _get_phase_label(pipeline_stage) that returns the label.
Files: langgraph_pipeline/web/routes/item.py

### D2: Expose phase_label in API responses
Addresses: P3, FR2
Satisfies: AC5, AC6, AC10
Approach: Add phase_label to both:
- The template context dict in the GET /item/{slug} handler
- The JSONResponse content in the GET /item/{slug}/dynamic handler
The value is computed via _get_phase_label(pipeline_stage). The existing 10-second
polling mechanism delivers updates without any new transport.
Files: langgraph_pipeline/web/routes/item.py

### D3: Fix Jinja template badge rendering
Addresses: P1, P2, FR1
Satisfies: AC1, AC2, AC3, AC7, AC8, AC9
Approach: Replace the stage badge Jinja block (item.html:1181-1196) to always
render phase_label as the badge text, using a "phase-badge" CSS class. Remove
the active_worker.current_task branch from badge rendering entirely -- the
current task info is already shown in the worker banner below. Remove the
"intake / planning" hardcoded fallback.
Files: langgraph_pipeline/web/templates/item.html

### D4: Fix JS stageBadgeHtml() for dynamic updates
Addresses: P2, P3, FR1, FR2
Satisfies: AC3, AC4, AC8, AC9, AC10
Approach: Update stageBadgeHtml() to accept phaseLabel from /dynamic JSON and
render it as the primary badge. Remove the worker.current_task branch and the
"intake / planning" fallback. The refresh() function passes data.phase_label
to stageBadgeHtml(). This ensures the badge updates every 10s poll cycle.
Files: langgraph_pipeline/web/templates/item.html

### D5: Phase badge CSS styling
Addresses: P1, FR1
Satisfies: AC2
Approach: Add a "phase-badge" CSS class with color-coded variants for each
phase. Use pill-shaped badges with phase-specific background colors that are
visually distinct from plan task items. Colors follow the existing palette:
- Intake/Claimed: amber (#fef3c7 bg, #92400e text)
- Requirements/Designing: purple (#ede9fe bg, #5b21b6 text)
- Planning: blue (#dbeafe bg, #1e40af text)
- Execution: green (#d1fae5 bg, #065f46 text)
- Verification: teal (#ccfbf1 bg, #134e4a text)
- Completed: blue same as existing status-completed
- Stuck: red (#fee2e2 bg, #991b1b text)
Files: langgraph_pipeline/web/templates/item.html

## Design -> AC Traceability Grid

| AC | Design Decision(s) | Approach |
|---|---|---|
| AC1 | D3 | Jinja renders phase_label as badge; plan item no longer shown as status |
| AC2 | D3, D5 | Phase badge has distinct "phase-badge" CSS class with phase-specific colors |
| AC3 | D3, D4 | Both Jinja and JS render phase badge instead of plan item as status indicator |
| AC4 | D4, D2 | JS stageBadgeHtml updates from phase_label delivered by /dynamic polling |
| AC5 | D1, D2 | Backend computes phase_label from pipeline_stage and exposes in JSON |
| AC6 | D2 | Existing 10s polling of /dynamic delivers phase_label without manual refresh |
| AC7 | D3, D1 | Badge shows human-readable name (Intake, Execution, etc.) from mapping |
| AC8 | D3, D4 | Badge visible throughout processing via both Jinja initial render and JS updates |
| AC9 | D3, D4 | Badge updates multiple times as /dynamic returns new phase_label each poll |
| AC10 | D4, D2, D1 | Badge reflects correct phase via mapping, auto-updates within poll interval |
