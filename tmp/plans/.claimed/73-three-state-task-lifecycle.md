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


## 5 Whys Analysis

Title: Add explicit "verified" status to clarify task validation completion

Clarity: 4/5

5 Whys:

W1: Why was the executor's behavior on crash recovery confusing?
    Because: Task 1.3 showed "completed" status, but validation hadn't yet run. The "completed" label implied the task was fully done, even though work was still pending. [C3, C4]

W2: Why couldn't the system tell that validation was still pending?
    Because: Tasks have only "completed" and "failed" states—there is no way to distinguish between a task that finished executing and one that also passed validation. Both map to the same "completed" label. [C1, C2]

W3: Why does the system need to distinguish these two events?
    Because: Downstream task selector needs to know whether dependent tasks can safely start, and it currently can't tell if a "completed" task still has pending validation. [C2, C11]

W4: Why is it unsafe to allow dependencies to proceed from execution-complete (pre-validation) tasks?
    Because: A task that has executed but hasn't passed validation might fail validation, and starting dependent work before that is caught creates unnecessary rework and cascading failures. [C2, C11] [ASSUMPTION: Validation failures must be surfaced before dependent tasks start]

W5: Why should "verified" become the authoritative terminal success state for dependency checking?
    Because: "Verified" is the only state that guarantees both execution succeeded AND validation passed (or wasn't required), making it the true signal that a task is fully complete and safe for dependents to start. [C11, C12]

Root Need: The system conflates execution completion with validation completion, creating ambiguity that breaks dependency correctness and makes crash recovery semantics unclear. The system needs "verified" as an explicit terminal success state so that only tasks confirmed to be fully correct can satisfy task dependencies. [C2, C3, C11, C12]

Summary: Add a "verified" state to separate execution completion from validation completion, ensuring dependencies only proceed when tasks are fully correct, not just when code has run.
