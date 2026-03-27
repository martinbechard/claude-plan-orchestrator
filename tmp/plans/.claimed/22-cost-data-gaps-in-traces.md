# Traces: incomplete cost data — many nodes missing cost metadata

## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


## Status: Open

## Priority: Medium

## Summary

Only execute_task and validate_task nodes record total_cost_usd in their
metadata_json. Other nodes that spawn Claude sessions (create_plan,
intake_analyze, verify_symptoms, verify_result) appear to have no cost
metadata. Additionally, many execute_task traces show total_cost_usd = 0.01
which looks like a default/dummy value rather than a real measurement.

## Evidence

    SELECT name, COUNT(*), SUM(json_extract(metadata_json, '$.total_cost_usd'))
    FROM traces
    WHERE json_extract(metadata_json, '$.total_cost_usd') > 0
    GROUP BY name;

    execute_task  1081  $39.60
    validate_task   48  $16.84
    (no other nodes)

Of the 1081 execute_task rows with cost > 0, many have exactly 0.01 —
suggesting a placeholder rather than actual API cost.

## Expected Behavior

Every node that invokes Claude (via call_claude or subprocess) should
record actual API cost in its trace metadata. The cost should come from
the Claude CLI JSON output (total_cost_usd field) not a hardcoded value.

## Fix

1. Audit all LangGraph nodes that spawn Claude — ensure each one extracts
   total_cost_usd from the subprocess JSON output and stores it in the
   trace metadata.
2. Fix the 0.01 default — find where this placeholder is set and replace
   with the actual cost from Claude's response.
3. Add cost recording to Slack intake LLM calls (call_claude in
   suspension.py) — these currently have no cost visibility at all.

## LangSmith Trace: 276bd081-0150-40ed-95a8-ca0a51726c2a
