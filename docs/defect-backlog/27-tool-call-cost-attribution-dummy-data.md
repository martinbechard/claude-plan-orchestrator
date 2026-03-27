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
