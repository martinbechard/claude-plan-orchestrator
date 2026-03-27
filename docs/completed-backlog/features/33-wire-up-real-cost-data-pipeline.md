# Wire up real cost data from pipeline workers to the analysis page

## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


## Status: Open

## Priority: High

## THIRD ATTEMPT — Previous two implementations were fake

This item has been "completed" twice and both times the implementation was
fake: test data was inserted into the DB, the page rendered it, the validator
accepted it. No real pipeline data ever flowed through.

## Problem

The /analysis page shows dummy data because:
1. _post_cost_to_api() only fires when LANGCHAIN_ENDPOINT is set to localhost
2. LANGCHAIN_ENDPOINT was never configured
3. The coder agent inserted test rows (12-test-item, cost=0.01, tokens=100/50)
4. The validator saw the page rendering and called it done

## What Must Actually Happen

1. Create a dedicated config for the web server URL (not LANGCHAIN_ENDPOINT).
   Read it from orchestrator-config.yaml or auto-detect during startup.
2. In task_runner.py and validator.py, POST cost records to the web server
   using the new config. Remove the LANGCHAIN_ENDPOINT dependency.
3. DELETE FROM cost_tasks WHERE item_slug = '12-test-item' to clean up fake
   data.
4. Run a real work item through the pipeline and verify /analysis shows
   that item's actual slug, actual cost, actual token counts.

## Acceptance Criteria (question form)

- After running one real work item, does the cost_tasks table contain a row
  with that item's slug and cost > $0.00? YES = pass, NO = fail
- Does the /analysis page show the real item slug (not "12-test-item")?
  YES = pass, NO = fail
- Is the web server URL configured automatically without requiring manual
  env var setup? YES = pass, NO = fail
- Are there zero rows in cost_tasks with item_slug="12-test-item"?
  YES = pass, NO = fail
- Does the cost value shown on /analysis match the cost in the completions
  table for the same item (within rounding)? YES = pass, NO = fail




## 5 Whys Analysis

**Title:** Real cost data never flows to the analysis page because of configuration dependency and incomplete validation

**Clarity:** 4 of 5 (clear problem statement, acceptance criteria well-defined, but the architectural failure across two previous attempts suggests the design issue wasn't fully surfaced upfront)

**5 Whys:**

1. **Why is the /analysis page showing dummy data instead of real cost data from the pipeline?**
   Because _post_cost_to_api() was never actually configured to post. It only fires when LANGCHAIN_ENDPOINT is set to localhost, which was never configured, so test data was manually inserted as a workaround instead.

2. **Why wasn't _post_cost_to_api() configured to post to the web server?**
   Because the implementation made the web server URL dependent on LANGCHAIN_ENDPOINT—an environment variable that was intended for the LangChain integration, not configured for cost reporting, and never set in the orchestrator environment.

3. **Why was the web server URL dependency tied to LANGCHAIN_ENDPOINT instead of a dedicated configuration?**
   Because the design conflated two separate concerns: the LangChain integration endpoint and the internal web server URL for cost reporting. They were treated as the same thing, so no separate config path was created.

4. **Why weren't these two concerns (LangChain vs. cost reporting) identified and separated during design?**
   Because the implementation approach started with "how do we post data somewhere" and reused an existing env var rather than first identifying all the distinct configuration needs and how they should be managed (orchestrator-config.yaml, auto-detection, etc.).

5. **Why did implementations pass validation twice without catching that real pipeline data never flowed through?**
   Because acceptance criteria validated only the output (does the page render?) rather than the mechanism (does real cost data flow through task_runner.py → validator.py → web server → cost_tasks table?). Endpoint-to-endpoint verification was never enforced.

**Root Need:** Establish a separate, explicit configuration path for cost reporting that is independent of LangChain setup, and enforce end-to-end acceptance criteria that verify real pipeline data flows through the actual mechanism, not just that the output page renders.

**Summary:** The feature fails because configuration was never set up and validation only checked output, not the actual data flow mechanism.
