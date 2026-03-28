# Trace detail: narrative view shows duplicate phases with 0.00s and "Unknown" labels

## Summary

The narrative view for a trace shows:
- Duplicate phases: "Planning" x2, "Execution" x2, "verify_fix" x2
  (from duplicate start/end trace events)
- All phases show 0.00s duration (no real timing data)
- "Unknown" label for verify_fix nodes (mapping incomplete)
- No information about what the agent did in each phase
- No cost per phase
- No link to the work item page or worker output logs

## Acceptance Criteria

- Are duplicate phases merged into single entries?
  YES = pass, NO = fail
- Does each phase show real duration (not 0.00s)?
  YES = pass, NO = fail
- Does verify_fix show as "Verification" (not "Unknown")?
  YES = pass, NO = fail
- Does each phase show cost? YES = pass, NO = fail
- Does each phase show a summary of what the agent did (files
  read/written, commands run)? YES = pass, NO = fail
- Is there a link to /item/<slug> from the trace detail?
  YES = pass, NO = fail
- Is there a link to worker output logs? YES = pass, NO = fail

## LangSmith Trace: a39730e4-db4d-4acc-a76a-b8a9263d0881


## 5 Whys Analysis

Title: Narrative view lacks trace event normalization and enrichment

Clarity: 4 (symptoms and acceptance criteria are clear; root diagnosis is partially embedded in the summary)

5 Whys:

1. Why do duplicate phases appear with 0.00s duration and Unknown labels?
   → Because the narrative view displays raw LangSmith trace events without preprocessing, deduplication, duration calculation, or name mapping.

2. Why doesn't the narrative view preprocess trace events before display?
   → Because the implementation renders the trace structure directly to the UI without an intermediate data transformation layer.

3. Why was no transformation layer built into the initial implementation?
   → Because the view was built as a minimum viable feature to validate trace display, with data normalization deferred to a second iteration.

4. Why was normalization deferred instead of included upfront?
   → Because the exact transformation rules needed (how to deduplicate start/end pairs, calculate phase duration, map phase types, compute costs) weren't fully specified before implementation started.

5. Why couldn't these transformation rules be specified upfront?
   → Because the trace schema, agent instrumentation approach, and phase structure were still evolving as the system matured, making it impossible to define complete normalization rules without validation against real trace data.

Root Need: **Define and implement a stable trace event normalization specification with clear deduplication, enrichment, and mapping rules so the narrative view can reliably transform raw trace events into clean, user-readable phase summaries.**

Summary: The narrative view needs a dedicated trace normalization layer to transform raw events into structured, deduplicated phases with real durations, cost data, action summaries, and proper navigation links.
