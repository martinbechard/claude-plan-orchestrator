# Rename misleading graph node names to reflect what they actually do

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
