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

## 5 Whys

1. Why do we need to capture raw worker output?
   Because when an item is completed badly, we cannot figure out what the
   agent actually did.

2. Why can't we figure out what the agent did?
   Because the console output (tool calls, file reads, Claude responses)
   only streams to the terminal and is not saved anywhere linked to the item.

3. Why isn't it saved linked to the item?
   Because the task logs (.claude/plans/logs/task-*.log) are timestamped
   but not indexed by item slug, and they only cover individual task
   executions not the full item lifecycle.

4. Why does this matter now?
   Because we have had multiple items completed with wrong designs, fake
   data, and missing features, and we could not diagnose why the agent
   chose poorly.

5. What is the root need?
   Save the raw agent output per item so a human can review exactly what
   happened — what files were read, what tools were called, what Claude
   said — and diagnose bad decisions to improve the pipeline.

## What We Need

- The full raw output that appears in the terminal during worker execution
  (the [Tool], [Claude], [Result] lines) must be saved to a file per item,
  indexed by slug so it can be found
- The file must be accessible from the work item detail page so we can
  drill down from "this item looks wrong" to "here's exactly what happened"
- The output must include ALL agent calls for that item: planner, coder,
  validator — not just one task
- This is about the RAW output — the actual tool calls, reads, edits, and
  Claude text responses. NOT a summary, NOT a JSON cost report, NOT
  additional logging or instrumentation. Save what already exists.

## Acceptance Criteria

- After a work item completes, does a file exist containing the raw console
  output from all agent calls for that item? YES = pass, NO = fail
- Can I navigate from the /item/<slug> page to view this raw output?
  YES = pass, NO = fail
- Does the output show the actual tool calls (Read, Edit, Bash, etc.) and
  Claude responses that were visible in the terminal during execution?
  YES = pass, NO = fail
- Does the output cover all phases (plan creation, task execution,
  validation) not just one task? YES = pass, NO = fail
- Is the output the raw existing stream, NOT a new custom logging format?
  YES = pass, NO = fail

## LangSmith Trace: 9ff1ec4c-dd8a-4176-89cf-1a68a721fc24
