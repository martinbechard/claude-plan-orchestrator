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




## 5 Whys Analysis

Title: Cost tracking incomplete and unreliable across pipeline nodes

Clarity: 4

5 Whys:

1. Why is cost data incomplete and unreliable in traces? — Because only execute_task and validate_task nodes record total_cost_usd from Claude API responses; other Claude-invoking nodes (create_plan, intake_analyze, verify_symptoms, verify_result) have no cost extraction code, and many execute_task rows show 0.01 (dummy) instead of real costs.

2. Why weren't all Claude-invoking nodes designed to capture costs, and where does the 0.01 default come from? — Because cost tracking was implemented as a point feature for specific high-priority nodes rather than as a universal pattern, and when actual cost extraction fails or returns empty, the code falls back to a hardcoded 0.01 default to avoid breaking the pipeline.

3. Why use a hardcoded default instead of surfacing the failure? — Because the system was designed to be resilient—cost data failures should not halt traces or block task execution. A placeholder value allows the pipeline to keep running even when cost measurement fails.

4. Why is pipeline resilience prioritized over accurate cost data? — Because costs are treated as secondary observability metadata rather than critical operational data. Task execution success is the primary goal; cost precision is desirable but not essential to core functionality.

5. Why wasn't cost tracking baked into the pipeline architecture from the start? — Because cost visibility was identified as a need after the initial pipeline was designed and built. It was retrofitted as a post-hoc observability feature rather than a foundational architectural requirement.

Root Need: Elevate cost tracking from optional observability to first-class data by designing a universal cost-capture pattern that applies to all Claude-invoking nodes, with explicit error handling and visibility (logging, flags) instead of silent defaults, ensuring costs are measured accurately and reliably across the entire pipeline.

Summary: Cost tracking was bolted onto specific nodes as a resilience-over-accuracy feature, creating gaps and unreliable data instead of being designed as a universal, measurable requirement from the start.
