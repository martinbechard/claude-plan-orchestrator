# Replace fragile build command with proper project-wide syntax check

## Summary

The build command in orchestrator-config.yaml hardcodes specific file paths
to compile. When files get deleted, the build fails. Replace with a
project-wide Python syntax check that automatically covers all .py files.

## Acceptance Criteria

- Does the build command check ALL .py files under langgraph_pipeline/?
  YES = pass, NO = fail
- Does it work without listing specific file paths?
  YES = pass, NO = fail
- Does it fail if any .py file has a syntax error?
  YES = pass, NO = fail

## LangSmith Trace: 449a921e-e973-4458-a144-984841c68ba1
