# Add "verified" task status to plan task lifecycle

Plan tasks currently have two terminal-ish states: "completed" (task code ran successfully) and "failed". There is no distinction between a task that finished executing and one that also passed validation.

This ambiguity surfaced during crash recovery: task 1.3 of item 71 had status "completed" but validation had not yet run. On resume, the executor re-validated 1.3 before moving to 2.1, which was correct but confusing because "completed" implied the task was fully done.

## Proposed states

- pending: not started
- in_progress: currently executing
- completed: code/agent finished successfully, awaiting validation
- verified: validation passed (or validation not configured for this task)
- failed: execution or validation failed
- skipped: deliberately skipped

## What changes

- Task selector should treat "verified" (not "completed") as the terminal success state when checking dependency satisfaction.
- Task runner should set status to "completed" after successful execution, then "verified" after validation passes.
- Dashboard task progress counts should show verified tasks as done.
- Existing plans with "completed" tasks (no validation configured) should be treated as "verified" for backward compatibility during the transition.

## LangSmith Trace: 598c1fd6-0545-4f27-9ba8-a977050d828e
