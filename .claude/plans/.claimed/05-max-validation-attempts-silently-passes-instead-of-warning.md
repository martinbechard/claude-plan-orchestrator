# Max validation attempts exceeded silently passes instead of warning

## Status: Open

## Priority: Medium

## Summary

When `max_validation_attempts` is exceeded in `validate_task`, the node returns
`last_validation_verdict: "PASS"` and logs "treating as PASS". This is wrong:
the task has failed validation every time it was checked and we simply gave up.
It should return `WARN` so the plan record reflects that validation was
inconclusive rather than successful.

## Root Cause

`validator.py` line 322:
```python
return {"last_validation_verdict": "PASS", "plan_data": plan_data}
```

`FAIL` cannot be used here because `retry_check` would attempt another task
execution, leading to an infinite loop (validator immediately exceeds the limit
again → FAIL → retry → repeat). `PASS` was chosen as the escape hatch but
silently hides the failure.

## Fix

Return `WARN` instead of `PASS`. `retry_check` treats any non-FAIL verdict as
`ROUTE_PASS`, so WARN exits the retry loop cleanly. The `validation_findings`
field already records the reason, so operators can see in the plan YAML that
validation was abandoned rather than passed.

Change line 319-322 in `langgraph_pipeline/executor/nodes/validator.py`:
```python
# before
return {"last_validation_verdict": "PASS", "plan_data": plan_data}

# after
return {"last_validation_verdict": "WARN", "plan_data": plan_data}
```

Also update the log message from "treating as PASS" to "treating as WARN".

## Verification Log

*(empty — no fix attempts yet)*

## LangSmith Trace: aa0d41fa-3f99-4d99-a458-3bf5cbfed913
