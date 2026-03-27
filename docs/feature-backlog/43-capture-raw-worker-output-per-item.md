# Capture raw worker console output per item for post-mortem review

## Status: Open

## Priority: High

## Summary

When investigating why a pipeline agent made a bad decision, we need to see
the raw console output — every tool call, every file read, every bash
command, every Claude response — that was produced during that item's
processing. This output already streams to the terminal during execution
but is not saved anywhere accessible after the worker finishes.

Without this, we cannot answer questions like "did the agent read the right
files?", "what model was used?", "was the frontend skill invoked?", or
"why did it choose approach A over approach B?"

## What We Need

- The full raw output that appears in the terminal during worker execution
  (the [Tool], [Claude], [Result] lines) must be saved to a file per item
- The file must be accessible from the work item detail page so we can
  drill down from "this item looks wrong" to "here's exactly what happened"
- The output must include ALL agent calls for that item: planner, coder,
  validator — not just one task

## Acceptance Criteria

- After a work item completes, does a file exist containing the raw console
  output from all agent calls for that item? YES = pass, NO = fail
- Can I navigate from the /item/<slug> page to view this raw output?
  YES = pass, NO = fail
- Does the output include the model name, tool calls, file reads, and
  Claude responses that were visible in the terminal during execution?
  YES = pass, NO = fail
- Does the output cover all phases (plan creation, task execution,
  validation) not just one task? YES = pass, NO = fail

## LangSmith Trace: 9ff1ec4c-dd8a-4176-89cf-1a68a721fc24
