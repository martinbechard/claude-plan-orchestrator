# Rename misleading graph node names to reflect what they actually do

## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


## Status: Open

## Priority: Medium

## Summary

Several graph node names are misleading, which confuses both humans reading
traces and AI agents that interpret the pipeline structure.

## Nodes to rename

- verify_symptoms → verify_fix: This node checks whether a defect fix
  worked (symptoms are gone), not whether symptoms exist. "Verify symptoms"
  sounds like it is confirming the bug is present.

- is_defect → route_after_execution: This is a routing edge that sends
  defects to verification and features to archive. The name suggests it
  is checking the item type, but it is actually deciding the post-execution
  path.

- has_items → route_after_scan: This is a routing edge from scan_backlog,
  not a boolean check. The name sounds like a predicate but it is a
  conditional edge router.

- after_intake → route_after_intake: Already somewhat clear but should
  match the naming pattern.

- after_create_plan → route_after_plan: Same pattern.

## Impact of bad names

- Traces show "verify_symptoms" which makes it look like the pipeline is
  verifying the bug exists rather than verifying the fix works
- AI agents reading the graph structure may misinterpret node purposes
- Humans reviewing traces waste time figuring out what each node does

## Acceptance Criteria

- Is verify_symptoms renamed to verify_fix in graph.py, the node function,
  trace metadata, and all references? YES = pass, NO = fail
- Do traces for a defect run show "verify_fix" instead of "verify_symptoms"?
  YES = pass, NO = fail
- Do all tests pass after the rename? YES = pass, NO = fail
- Are the edge function names updated consistently? YES = pass, NO = fail




## 5 Whys Analysis

Title: Graph node names must accurately reflect actual behavior to enable correct interpretation
Clarity: 4

5 Whys:
1. Why are these node names misleading? Because the names reflect what each node was originally intended to do or a partial aspect of its behavior, rather than what it actually does. "verify_symptoms" sounds like it's checking that a bug exists, when it actually verifies the fix worked (symptoms are gone).

2. Why does this create problems? Because humans reading execution traces and AI agents analyzing the graph structure rely on node names to understand pipeline intent and flow. Misleading names cause them to form incorrect mental models, waste time reverse-engineering actual behavior, and potentially make wrong decisions about system extension.

3. Why is this especially critical for AI agents? AI agents don't read source code to infer intent—they rely entirely on structural metadata like node names, connections, and trace context. An agent seeing "verify_symptoms" might place diagnostic logic or reasoning in the wrong node, or suggest extending the pipeline incorrectly.

4. Why is naming becoming more critical now? The pipeline moved from development to operational use with trace monitoring (LangSmith), multiple human reviewers, and AI agents reasoning about structure. During development, the single developer holds the real behavior in memory. Once externally referenced, node names become the shared contract others depend on.

5. Why is accurate naming fundamental to workflow systems? Workflows are graphs that people and systems *read* to understand intent without inspecting code. Node names are the primary metadata encoding "what happens here." With many nodes and branches, each misleading name compounds cognitive load exponentially for all readers.

Root Need: The pipeline's node names must match their actual behavior so that human operators, AI agents, and future maintainers can correctly interpret pipeline intent and flow from traces and structure alone, without reading implementation code.

Summary: Naming accuracy is the interface contract between the pipeline's structure and those who read it.
