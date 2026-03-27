# Work item page: show validator results and what changed

## Summary

After an item completes, the work item page shows cost and duration but
nothing about what actually happened. A user looking at the page cannot
tell if the fix was applied, if validation passed, or what was checked.

The page needs to show:

1. Validator verdict for each task (PASS/WARN/FAIL) and the findings
2. What files were modified (git diff summary)
3. The task execution summary (which tasks ran, which were skipped)

## Where the data is

- Validator output is in the task log files (tmp/plans/logs/task-*.log)
  and in the worker output files (docs/reports/worker-output/<slug>/)
- The plan YAML with task statuses is deleted on archive — this should
  be preserved or the final task statuses should be saved to the
  completion record
- Git commits made by the worker have the item slug in the message

## Acceptance Criteria

- Does the completed item page show the validator verdict (PASS/WARN/FAIL)
  for each task that was executed? YES = pass, NO = fail
- Does it show which files were modified by the execution?
  YES = pass, NO = fail
- Can the user tell at a glance whether the item was properly fixed or
  just marked complete without real work? YES = pass, NO = fail
