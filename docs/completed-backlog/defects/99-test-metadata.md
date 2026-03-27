# Test item: verify trace metadata and velocity are populated

## Summary

Verify that execute_task traces contain real token counts and cost in
metadata_json (not 100/50/0.01 or NULL), and that the velocity badge
appears on the item detail page.

## What To Do

Add a comment "# metadata test" to langgraph_pipeline/shared/paths.py
(after the existing header comment).

## Acceptance Criteria

- After execution, does the traces DB contain a row for this item's
  execute_task with input_tokens > 100 and output_tokens > 100?
  YES = pass, NO = fail
- Does the item detail page show a velocity badge with a non-zero value?
  YES = pass, NO = fail
- Does the completions table have tokens_per_minute > 0 for this item?
  YES = pass, NO = fail




## 5 Whys Analysis

Title: Verify that recent trace metadata fix reliably captures real token counts through the full system
Clarity: 3/5

5 Whys:
1. Why add a comment marker to paths.py and run these specific checks?
   - A recent fix changed how trace metadata is written (directly to proxy DB instead of through SDK batching), and we need to verify it actually works.

2. Why was the SDK batching approach causing problems?
   - It was dropping or corrupting token count data—either leaving it NULL or substituting placeholder defaults (100/50/0.01) instead of capturing real values.

3. Why does accurate token count matter if it's just in the database?
   - Token counts flow downstream to cost calculations, velocity metrics, and performance tracking—if the source data is wrong, all downstream insights are unreliable.

4. Why do we care about reliability in metrics if the fix is already in the code?
   - Code-level correctness doesn't guarantee end-to-end data flow works—traces must actually be stored, read correctly, computed into metrics, and displayed on the UI without breaking at any step.

5. Why is it critical to verify this now rather than waiting for user reports?
   - The system's core value is observability into AI execution costs and efficiency; if metrics are silently wrong, users make decisions on false data without knowing it.

Root Need: Confirm that bypassing the unreliable SDK batching mechanism actually solves the root problem—that real token counts now flow reliably through the entire observability chain (execution → trace capture → database → metrics → UI).

Summary: The recent architectural fix requires end-to-end verification that trace metadata now captures real data instead of defaults or nulls across the full system pipeline.
