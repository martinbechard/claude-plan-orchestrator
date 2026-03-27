# Work Item Status Clarity - Design Document

## Overview

Feature 17 requests clear real-time status visibility on the /item/<slug> page.
The majority of this feature was already implemented in a prior iteration. This
plan covers validation of the existing implementation and fixing any gaps found
against the acceptance criteria in the backlog item.

## Current State

The following are already implemented in item.py and item.html:

- Pipeline stage derivation via _derive_pipeline_stage() waterfall
- Stage constants: executing, completed, planning, claimed, designing, queued, stuck, unknown
- CSS status badges for all stages
- Active worker banner with PID, elapsed time, current task, and trace link
- Plan task progress indicator ("X / Y" completed count above task list)
- Auto-refresh every 10 seconds for non-terminal stages

## Gaps to Validate and Fix

1. **Validating stage**: The backlog item lists "Validating (validator running)" as
   a required stage. The current implementation has no _STAGE_VALIDATING constant
   and no logic to detect when a validator is the active task. The validator runs
   as a plan task, so "executing" is shown instead. Need to check if the active
   worker's current_task can distinguish validation from normal execution.

2. **Stage label clarity**: The backlog asks the page to answer "what is happening
   with this item right now?" -- verify the stage badges and any contextual
   messages are clear enough for non-technical users.

3. **Progress indicator**: Confirm the "X / Y" indicator is visible and meaningful
   alongside the task list (not just raw checkboxes).

## Key Files

- langgraph_pipeline/web/routes/item.py -- route handler and stage derivation
- langgraph_pipeline/web/templates/item.html -- template with badges and task list
- langgraph_pipeline/web/dashboard_state.py -- WorkerInfo and active_workers

## Design Decisions

- The "Validating" stage can be derived from the active worker's current_task
  field: if the current task name contains "validat" or the task agent is
  "validator", the stage should show as "validating" instead of "executing".
  This is a refinement of the existing executing stage, not a new waterfall step.
- No database schema changes are needed; all state is derived from filesystem
  and DashboardState.
