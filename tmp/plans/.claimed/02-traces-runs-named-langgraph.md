# Traces page: all runs named "LangGraph" with slug "LangGraph"

## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.

## Summary

Every root trace in the LangSmith proxy is named "LangGraph" and the slug
column also shows "LangGraph". This makes the traces list completely
unreadable — there is no way to tell which run corresponds to which work item.

## Acceptance Criteria

- Do root traces in the DB have names that match the actual work item slug
  (not "LangGraph")? Run: SELECT DISTINCT name FROM traces WHERE
  parent_run_id IS NULL ORDER BY created_at DESC LIMIT 10;
  YES (slugs visible) = pass, NO (all say "LangGraph") = fail
- Does the /proxy traces list page show the item slug in the Name column
  instead of "LangGraph"? YES = pass, NO = fail
- Can I filter traces by slug name and get meaningful results?
  YES = pass, NO = fail




## 5 Whys Analysis

Title: Root traces in LangSmith proxy show generic "LangGraph" name instead of work item slug

Clarity: 4/5 (Clear acceptance criteria, but root cause not explained)

5 Whys:

1. Why is the traces list unreadable?
   Because all root traces display the same generic name "LangGraph" instead of showing the actual work item slug they're executing, making it impossible to visually distinguish which trace corresponds to which work item.

2. Why are traces created with the hardcoded name "LangGraph" rather than the work item slug?
   Because the code that creates root traces in the LangSmith proxy integration doesn't capture or pass the work item slug when initializing traces with the LangSmith API.

3. Why isn't the work item slug available when the trace is created?
   Because the execution context—which work item is currently running—either isn't being captured at trace creation time, or isn't being passed from the orchestrator/job runner to the LangGraph integration layer.

4. Why doesn't work item context flow from the job orchestrator to the tracing layer?
   Because the orchestrator and LangGraph integration were built as separate subsystems without an explicit contract to share work item metadata, so there's no mechanism to thread the work item slug through to trace initialization.

5. Why wasn't this traceability requirement built into the architecture from the start?
   Because observability needs (correlating traces to source work items) weren't prioritized during the initial LangSmith integration design, which treated tracing as an optional monitoring layer rather than a core observability requirement.

Root Need: The system needs to propagate work item identity (slug) from the orchestrator through to LangSmith trace creation, so that execution traces are automatically labeled with their source work item and users can identify and navigate between work items and their traces.

Summary: Traces lack work item identification because the orchestrator doesn't pass the work item slug to the LangSmith tracing layer at trace creation time.

## LangSmith Trace: 9b79ceed-69ed-4c15-9245-9e3dd9ad5655
