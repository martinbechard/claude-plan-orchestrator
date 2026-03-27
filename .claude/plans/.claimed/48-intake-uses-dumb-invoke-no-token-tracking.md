# Intake and planner use _invoke_claude which doesn't track tokens

## Summary

The intake analysis (_invoke_claude) and planner (_run_subprocess) use
simple subprocess.run calls that don't capture token counts or stream
output. The executor uses _run_claude which streams, captures tool calls,
and records tokens. This means intake and planning phases show 0 velocity
on the dashboard and have no token tracking.

All Claude invocations should use the same streaming path so tokens are
tracked consistently across all pipeline phases.

## Acceptance Criteria

- Does the dashboard show non-zero velocity during the intake phase?
  YES = pass, NO = fail
- Does the dashboard show non-zero velocity during the planning phase?
  YES = pass, NO = fail
- Are intake and planner token counts included in the item's total
  token count? YES = pass, NO = fail

## LangSmith Trace: fb95fae6-1ee2-475f-8fbf-9ff9296cc582
