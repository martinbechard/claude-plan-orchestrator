# Tool-call cost attribution for individual Read/Edit/Bash calls

## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


## Status: Open

## Priority: Low

## Summary

Individual tool calls (Read, Edit, Write, Bash, Glob, Grep, Skill) have no
cost data in their trace metadata. While these tools are technically free
API operations, each one contributes to the token count of the parent LLM
call (the tool result is fed back into the context window). Users asking
"how much does a Read call cost?" cannot get an answer today.

## Current State

- 1,557 tool call traces in the DB (Read 349, Bash 337, Edit 185, etc.)
- None have total_cost_usd, input_tokens, or output_tokens in metadata
- Cost is only recorded at the parent execute_task/validate_task level

## Expected Behavior

Each tool call should have an estimated cost attribution based on the
token overhead it added to the parent LLM conversation:
- result_bytes or result_tokens from the tool output
- Estimated cost = result_tokens * per-token rate for the parent's model

This is an estimate (the exact marginal cost of adding tokens to context
depends on caching, position, etc.) but it gives users directional insight
into which tool calls are expensive.

## Implementation Options

1. At trace recording time: when the pipeline records a tool_use trace,
   include the result size (bytes or estimated tokens) in metadata. The
   cost analysis page computes the estimated cost using model pricing.

2. Post-hoc: a background job or the cost analysis page itself estimates
   tool cost by dividing the parent's total cost proportionally across
   its child tool calls based on result size.

Option 2 is simpler and requires no pipeline changes.

## LangSmith Trace: f2acd423-9088-4eff-bd49-45a943a6aa2f


## 5 Whys Analysis

Title: Tool-call cost attribution for individual Read/Edit/Bash calls

Clarity: 4

5 Whys:
1. Why don't individual tool calls have cost data tracked?
   - Cost attribution was only implemented at the parent task level (execute_task, validate_task) rather than at the granular tool-use level.

2. Why is it important for users to see individual tool call costs?
   - When pipeline runs seem expensive, users need to identify which specific operations (Read, Bash, Glob, etc.) consumed the most tokens to understand where to optimize.

3. Why do users need to know where their tokens are going?
   - The orchestrator runs frequently in an autonomous loop. If users know which operations are expensive, they can refactor to use cheaper alternatives or combine operations more efficiently.

4. Why does per-run optimization matter for the orchestrator?
   - Because the system iterates repeatedly over many work items; small inefficiencies in a single run compound across dozens or hundreds of executions, creating measurable cost and latency impact.

5. Why is understanding cost distribution critical for autonomous system design?
   - To make informed architectural decisions about tool selection and pipeline structure—e.g., one large Bash call vs. many small Glob calls, which directly affects the system's cost efficiency and scalability as it processes items at scale.

Root Need: Users need operation-level cost visibility to identify and eliminate inefficiencies in the frequently-executing autonomous orchestrator, where small per-run overhead compounds into significant cost and performance impact.

Summary: The orchestrator's autonomous, repeating architecture requires granular cost data to enable users to optimize tool usage patterns and control cumulative cost drift.
