# Test: live stats on item page

## Summary

Add a comment "# live stats test" to langgraph_pipeline/shared/paths.py.

## Acceptance Criteria

- Does the item page show non-zero Cost and Tokens WHILE the item is
  still running (before completion)? YES = pass, NO = fail
- Does the velocity badge appear during execution?
  YES = pass, NO = fail




## 5 Whys Analysis

Title: Verify live metrics display in real-time during task execution

Clarity: 2/5

5 Whys:

1. Why are we adding a comment "# live stats test" to paths.py instead of implementing the actual feature?
   - Answer: The comment appears to be a marker documenting that this file is part of the live stats feature, but the acceptance criteria describe testing user-facing functionality rather than a code comment—this mismatch suggests the actual feature may already be implemented (the recent `/api/worker-stats` endpoint), and this is marking the involvement of the paths file.

2. Why do we need to verify that Cost and Tokens display while the item is still running?
   - Answer: Because the feature's entire purpose is to provide real-time visibility into resource consumption, so we must confirm the data actually appears on the page during execution, not just after completion.

3. Why is real-time Cost and Token visibility important specifically during execution?
   - Answer: So users can monitor whether a running task is consuming resources as expected and detect inefficiencies or unexpected behavior before the task finishes, rather than discovering problems only after completion.

4. Why can't users wait until the task completes to see Cost and Token data?
   - Answer: Because long-running or expensive tasks need oversight—users need to see metrics mid-execution to make early decisions about whether to continue or stop the task.

5. Why is early decision-making capability critical for this system?
   - Answer: Because without real-time visibility, users cannot detect runaway costs, detect performance anomalies, or exercise control over resource consumption until it's too late, leading to wasted money and time.

Root Need: Enable users to monitor resource consumption and task performance in real-time while tasks are running, allowing them to make informed decisions about task continuation or termination before tasks complete.

Summary: The system needs to display live Cost, Tokens, and velocity metrics during task execution so users can detect inefficiencies and control costs in real-time rather than discovering problems retroactively.
