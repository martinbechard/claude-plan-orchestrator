# Tool call cost attribution displays dummy data — replace with real implementation

## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


## Status: Open

## Priority: High

## Summary

The tool call cost attribution section on the cost analysis page shows dummy
placeholder data instead of real values. The dummy data needs to be deleted
and the attribution must be implemented by extracting actual tool call costs
from the pipeline execution data.

## Fix

1. Find and delete all dummy/hardcoded tool call cost data (likely seeded
   during the initial feature implementation that was marked complete
   prematurely).
2. Implement real cost attribution within the pipeline scripts: when a
   worker executes tool calls (Read, Edit, Write, Bash, etc.), compute the
   estimated cost contribution of each tool call based on the token overhead
   it adds to the parent LLM context.
3. Store the per-tool-call cost attribution in the traces DB or cost_tasks
   table so the analysis page can query and display it.
4. Update the analysis page to read from the real data source.

## Related Items

- Feature 11 (tool-call-cost-attribution): design spec for the attribution
  approach — use proportional token allocation from parent agent cost.
- Defect 22 (cost-data-gaps-in-traces): tool calls have no cost metadata
  in their trace records.
- Feature 03 (cost-analysis-db-backend): the cost_tasks table has only
  fake test data.

## LangSmith Trace: df450b06-c72f-45fe-a72e-6ba2e7221a28


## 5 Whys Analysis

Title: Tool call cost attribution displays dummy data instead of real pipeline costs

Clarity: 4 (well-defined problem and scope, though acceptance criteria for "complete" could be more explicit)

5 Whys:

1. Why is dummy data displayed instead of real tool call costs?
   — Because the feature implementation stops at the UI layer; the backend pipeline logic to extract and store actual tool call costs from LLM execution traces hasn't been integrated with the display component.

2. Why hasn't the backend cost extraction pipeline been integrated?
   — Because the feature was marked complete based on the frontend component being functional, without verifying that real data was flowing through the entire system end-to-end.

3. Why was the feature marked complete without end-to-end data validation?
   — Because the completion criteria focused on "UI can display cost data" rather than "UI displays real cost data sourced from production pipeline," treating them as equivalent.

4. Why weren't real-data requirements part of the acceptance criteria?
   — Because the feature had upstream data dependencies (trace cost metadata, cost_tasks table population) that were listed as related but not treated as hard blocking requirements for completion.

5. Why aren't upstream dependencies enforced as completion blockers?
   — Because there's no gating mechanism preventing a consumer feature from being marked done until its data source dependencies are implemented, tested, and verified working.

Root Need: Establish a feature completion workflow that enforces upstream dependency validation and requires end-to-end data flow verification before marking features done.

Summary: Tool call costs show dummy data because features were marked complete at the UI layer without waiting for backend data pipelines and upstream dependencies to be ready.
