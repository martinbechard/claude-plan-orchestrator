# Parallel tasks not validated before dependents are checked

When a parallel group of tasks completes, the executor moves on to independent tasks in other sections without first validating parallel tasks that require validation. This creates a permanent deadlock for dependent tasks.

## Reproduction

Item 74-item-page-step-explorer: tasks 0.1, 0.2, 0.3 ran in parallel (design-phase0). Task 0.3 (agent=frontend-coder) is in the validation run_after list but was never validated (validation_attempts=0). Its effective_status remained "completed" instead of "verified". Task 0.4 depends on 0.1+0.2+0.3, so it was permanently blocked. The executor moved on to section 1 tasks (1.1, 1.2 which had no dependencies) then deadlocked when it returned to check 0.4.

## Expected behavior

After a parallel group completes, the executor should validate each task that requires validation before evaluating dependencies for the next batch of tasks.

## Affected code

- langgraph_pipeline/executor/nodes/task_selector.py - find_next_task logic
- langgraph_pipeline/executor/nodes/validator.py - validate_task invocation




## 5 Whys Analysis

Title: Executor skips validation of parallel tasks before checking dependents

Clarity: 4/5 (well-structured with specific facts and trace reference; mechanism could be slightly clearer)

5 Whys:

W1: Why are dependent tasks permanently blocked?
    Because task 0.4 depends on 0.1+0.2+0.3, but task 0.3 was never validated and remained in "completed" instead of "verified" status. [C3, C6, C7]

W2: Why was task 0.3 never validated despite being in the validation run_after list?
    Because the executor's find_next_task logic doesn't systematically validate tasks from a completed parallel group before moving to other sections. [C5, C2, C10]

W3: Why does the executor move on to other independent tasks (section 1) instead of validating the parallel group first?
    Because the task selection algorithm prioritizes finding any ready task without enforcing a rule that parallel group validation must complete before checking dependencies for dependent tasks. [C2, C4]

W4: Why doesn't the executor recognize that task 0.4's dependency (0.3) is incomplete?
    Because it checks task status but doesn't distinguish between "completed" (not validated) and "verified" (validated) when evaluating whether dependencies are satisfied. [C6, C9]

W5: Why doesn't the validation run_after list prevent this from happening?
    Because run_after identifies which tasks need validation, but the task selector doesn't consult this information to prioritize validation before dependency evaluation. [C5, C2] [ASSUMPTION: run_after metadata exists but isn't wired into task selection logic]

Root Need: The executor must enforce a validation phase immediately after a parallel group completes, validating all tasks with run_after requirements before evaluating dependencies for subsequent tasks. This ensures tasks can only unblock dependents after they reach "verified" status, not just "completed". [C1, C2, C9]

Summary: The task selection algorithm prioritizes finding any available ready task instead of validating completed parallel tasks first, breaking the dependency guarantee for dependent tasks.
