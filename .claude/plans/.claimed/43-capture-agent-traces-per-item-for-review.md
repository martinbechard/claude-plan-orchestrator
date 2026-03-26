# Capture detailed agent traces per work item for post-mortem review

## Status: Open

## Priority: High

## Summary

When a pipeline agent makes a bad design decision (e.g. using a collapsible
region instead of a tooltip for disclaimer text), there is no way to review
the agent's reasoning after the fact. We need per-item trace files that
capture the full conversation — what model was used, what skills were invoked,
what design choices were considered — so bad decisions can be diagnosed.

## Problem

Item 36 (cost analysis UI polish) produced a design that uses a collapsible
region for two disclaimer lines instead of a simple tooltip/info bubble.
We cannot determine:
- Was the frontend-design skill actually invoked?
- What model was used (haiku? sonnet? opus?)?
- What design alternatives were considered?
- What prompts led to this decision?

## Expected Behavior

For each work item processed by the pipeline, save a trace file that
includes:
- The model used for each agent call (planner, coder, validator)
- Which skills were invoked (or not invoked)
- The design document produced and any alternatives considered
- The full prompt sent to each agent
- The full response from each agent (or a summary if too large)
- Decision points: why option A was chosen over option B

## Trace File Location

Save to docs/reports/item-traces/<slug>.md or .json, one per work item.
This is separate from the LangSmith traces (which track node execution)
— this is about capturing the reasoning and decision quality.

## Acceptance Criteria

- After processing a work item, does a trace file exist at the expected
  location with the model name and skill invocations? YES = pass, NO = fail
- Can a human read the trace file and understand why a particular design
  decision was made? YES = pass, NO = fail
- Does the trace file indicate which frontend skill was used for UI items?
  YES = pass, NO = fail

## LangSmith Trace: 82468b41-c95f-49ce-97e8-3699052e4ee2
