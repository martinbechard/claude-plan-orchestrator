# Executor silently returns when all remaining tasks are blocked

When the executor's find_next_task finds pending tasks but none are eligible (all blocked by unsatisfied dependencies), it returns as if execution is complete. There is no error, warning, or distinct outcome indicating that tasks were left unfinished due to a deadlock.

## Reproduction

Item 74-item-page-step-explorer: after tasks 1.1 and 1.2 completed, the executor checked for the next task. Tasks 0.4 and 0.5 were pending but blocked (0.3 not validated). The executor returned silently, the pipeline continued to archive, and the item was recorded as success.

## Expected behavior

When pending tasks exist but none have satisfied dependencies, the executor should detect this as a deadlock condition and either:
- Report an error/warning with the list of blocked tasks and their unsatisfied dependencies
- Set a distinct outcome (e.g. "deadlock") so the pipeline can handle it appropriately
- At minimum, log a clear warning identifying which tasks are blocked and why

## Affected code

- langgraph_pipeline/executor/nodes/task_selector.py - find_next_task deadlock detection (line ~268 logs a message but the executor loop still exits cleanly)




## 5 Whys Analysis

Title: Executor silently archives items with blocked tasks instead of reporting deadlock

Clarity: 4

5 Whys:

W1: Why does the executor return silently without reporting the actual execution state?
    Because: The find_next_task function doesn't distinguish between "all tasks completed successfully" and "pending tasks exist but are all blocked by unsatisfied dependencies" [C1, C2]

W2: Why is this distinction missing?
    Because: When find_next_task examines remaining work, it finds pending tasks (C5) but checks only whether they are *eligible* to run, not whether they form a solvable dependency graph [C2]

W3: Why does the pipeline then archive the item as success?
    Because: The executor's clean return is interpreted as successful completion—there is no error signal, warning, or distinct outcome to indicate incomplete work [C3, C6]

W4: Why is there a gap between the log message and the pipeline's action?
    Because: The log at line 268 exists (C11) but is insufficient—the executor loop still exits cleanly without raising an error or setting a distinct outcome that the pipeline checks [C11]

W5: Why is this a problem worth fixing?
    Because: Blocked tasks represent failed execution—tasks that *should* run but cannot due to broken dependencies—and silently archiving them hides the failure, making the item appear successful when it is not [C1, C7] [ASSUMPTION: that blocked tasks indicate a real failure condition, not expected behavior]

Root Need: The executor must detect when pending tasks cannot proceed due to circular or unsatisfied dependencies (C1, C2) and surface this explicitly (C7, C8, C9) as an error condition rather than silent completion, so the pipeline can distinguish between true success and deadlock.

Summary: The executor silently treats deadlocked (blocked-pending) tasks as completion success, requiring explicit deadlock detection and outcome signaling to prevent silent data loss.
