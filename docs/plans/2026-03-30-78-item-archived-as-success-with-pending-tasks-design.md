# Design: 78 Item Archived As Success With Pending Tasks

Source: tmp/plans/.claimed/78-item-archived-as-success-with-pending-tasks.md
Requirements: docs/plans/2026-03-30-78-item-archived-as-success-with-pending-tasks-requirements.md

## Architecture Overview

The archival node (langgraph_pipeline/pipeline/nodes/archival.py) currently commits
the archive outcome based solely on item type and verification history. It never
inspects the plan YAML to check whether all tasks reached terminal status. This
allows items with pending or blocked tasks to be silently archived as success.

The fix adds a pre-commit validation gate inside the archival node that reads the
plan YAML, enumerates all tasks, and checks each against a defined set of terminal
statuses. When non-terminal tasks are found, the outcome is downgraded from
"completed" to "incomplete" and the specific non-terminal tasks are recorded in
both the Slack notification and the worker-output directory.

## Key Files

- MODIFY: langgraph_pipeline/pipeline/nodes/archival.py -- add validation gate,
  new outcome constant, and non-terminal task reporting
- MODIFY: tests/langgraph/pipeline/nodes/test_archival.py -- add tests for the
  new validation logic and outcome behavior

## Design Decisions

### D1: Pre-archive task status enumeration

Addresses: P1, FR1
Satisfies: AC1, AC2, AC5, AC6
Approach: Add a helper function _find_non_terminal_tasks(plan_path) that reads the
plan YAML, iterates all tasks across all sections, and returns a list of
(task_id, task_name, task_status) tuples for tasks whose status is NOT in the
ARCHIVE_TERMINAL_STATUSES constant. The constant is defined as exactly
{"verified", "failed", "skipped"} per AC6. This function is called early in the
archive() node, before outcome determination.

When plan_path is None or the file cannot be read, the function returns an empty
list (no tasks to flag). This mirrors the existing graceful-degradation pattern
used by _preserve_plan_yaml and _remove_plan_yaml.

Files: langgraph_pipeline/pipeline/nodes/archival.py

### D2: Outcome gating on task terminal status

Addresses: P2, FR1
Satisfies: AC3, AC4, AC7
Approach: Introduce a new outcome constant ARCHIVE_OUTCOME_INCOMPLETE = "incomplete"
alongside the existing "completed" and "exhausted" outcomes. Modify the
_determine_outcome() function signature to accept an optional non_terminal_tasks
parameter. When this list is non-empty, the function returns ARCHIVE_OUTCOME_INCOMPLETE
regardless of item type or verification history. This prevents any item from being
archived as success when tasks remain pending or blocked.

The existing logic for "completed" vs "exhausted" is preserved as the fallback
when all tasks are terminal.

Files: langgraph_pipeline/pipeline/nodes/archival.py

### D3: Non-terminal task reporting in output and notifications

Addresses: FR2
Satisfies: AC8, AC9, AC10
Approach: Three reporting channels ensure visibility:

1. Slack notification: Extend _build_slack_message() to handle the "incomplete"
   outcome with a warning-level message that lists the non-terminal task IDs
   and their statuses.

2. Worker-output artifact: Write a summary file (archive-warnings.txt) to the
   worker-output directory (docs/reports/worker-output/{slug}/) containing the
   full list of non-terminal tasks. This satisfies AC10 (persisted in archived
   output, not just transient logs).

3. Console output: Print the non-terminal task list to stdout for pipeline
   operator visibility during execution (existing pattern in archive()).

Files: langgraph_pipeline/pipeline/nodes/archival.py

## Design -> AC Traceability Grid

| AC | Design Decision(s) | Approach |
|---|---|---|
| AC1 | D1 | _find_non_terminal_tasks reads plan YAML and inspects every task status |
| AC2 | D1 | Returns non-terminal tasks when any task status is not in ARCHIVE_TERMINAL_STATUSES |
| AC3 | D2 | _determine_outcome returns "incomplete" when non_terminal_tasks is non-empty, blocking success |
| AC4 | D2 | Gate applies regardless of how execution ended (deadlock, normal return, etc.) |
| AC5 | D1 | Enumerates all tasks across all sections, checking each against terminal set |
| AC6 | D1 | ARCHIVE_TERMINAL_STATUSES defined as exactly {"verified", "failed", "skipped"} |
| AC7 | D2 | ARCHIVE_OUTCOME_INCOMPLETE returned instead of ARCHIVE_OUTCOME_SUCCESS |
| AC8 | D2, D3 | Outcome is "incomplete" (not "completed") when pending tasks remain; Slack shows warning level |
| AC9 | D3 | Slack message and archive-warnings.txt list specific task IDs, names, and statuses |
| AC10 | D3 | archive-warnings.txt written to worker-output directory (persistent artifact) |
