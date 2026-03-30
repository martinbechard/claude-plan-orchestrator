# Worker reports $0.00 cost despite performing work

The first execution of item 74-item-page-step-explorer ran for 25 minutes, executed intake analysis (clause extraction, 5 Whys), plan creation with validation, and multiple executor tasks (0.1, 0.2, 0.3, 1.1, 1.2), but reported cost_usd=0.0 in the completion record.

## Root cause hypothesis

The worker reads session_cost_usd from the final pipeline state to report cost. Costs from early pipeline nodes (intake, requirements, plan creation) may not be properly accumulated into this field across node boundaries, or the cost accumulation was reset when the executor subgraph ran.

## Expected behavior

The reported cost should reflect all API calls made during the worker's execution, including intake analysis, plan creation, validation, and task execution.

## Affected code

- langgraph_pipeline/worker.py - cost extraction from final_state
- langgraph_pipeline/pipeline/nodes/intake.py - cost accumulation
- langgraph_pipeline/pipeline/nodes/plan_creation.py - cost accumulation
- langgraph_pipeline/pipeline/nodes/execute_plan.py - cost mapping from executor to pipeline state

## LangSmith Trace: d507da1b-7ea9-4e24-821a-2b990e327d64


## 5 Whys Analysis

Title: Worker cost reporting shows $0.00 despite significant API usage

Clarity: 4

5 Whys:

W1: Why was cost reported as $0.00?
    Because the worker reads session_cost_usd from the final pipeline state and that value is 0 [C3, C1]

W2: Why is session_cost_usd = 0 in the final pipeline state?
    Because costs from early pipeline nodes (intake, plan creation) may not be properly accumulated into this field across node boundaries, or the cost field was reset when the executor subgraph ran [C4, C2]

W3: Why aren't costs being accumulated properly across node boundaries?
    Because the pipeline has multiple independent nodes (intake, plan_creation, executor) that each track costs separately, and there may not be a consistent accumulation pattern merging costs from one node to the next [C7, C8, C9]

W4: Why doesn't the executor subgraph properly propagate costs back to the parent pipeline state?
    Because the executor is a separate subgraph with its own state management, and the cost mapping logic in execute_plan.py may not be merging executor costs with costs already accumulated from earlier nodes [C9, C6]

W5: Why wasn't this end-to-end cost flow tested or validated before executor integration?
    Because there is no verification that session_cost_usd correctly accumulates through all pipeline stages and arrives intact in the final state that the worker reads [C5] [ASSUMPTION]

Root Need: Implement validated cost accumulation across all pipeline nodes (intake, plan creation, executor) to ensure session_cost_usd in the final state reflects all API calls performed during worker execution, enabling accurate cost reporting [C1, C4, C5]

Summary: Cost tracking fails to accumulate across pipeline node boundaries, causing the worker to report $0.00 for work that consumed significant API resources.
