# Console output section should display the full log file content

## Summary

The Console Output section at the bottom of the work item page shows
very limited information. It should display the actual log file content
— the full raw output with tool calls, Claude responses, and timestamps
that was captured during execution.

The log files already exist at docs/reports/worker-output/<slug>/ with
one file per pipeline phase (intake, planner, task execution). The page
should render their content inline (or in a scrollable panel) instead of
the current minimal view.

## Acceptance Criteria

- Does expanding Console Output show the full raw log content from
  the worker output files? YES = pass, NO = fail
- Can I see tool calls ([Tool] Read, [Tool] Bash etc) and Claude
  responses ([Claude] ...) in the expanded view? YES = pass, NO = fail
- Is the content displayed in a monospace scrollable panel with
  reasonable max-height? YES = pass, NO = fail
- Are all phases shown (intake, planner, execute, validate) not just
  one? YES = pass, NO = fail
