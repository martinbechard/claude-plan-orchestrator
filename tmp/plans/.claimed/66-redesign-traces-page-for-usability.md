# Redesign traces page: item-centric execution view instead of raw LangSmith traces

## Summary

The current traces page shows raw LangSmith trace data — rows called
"LangGraph", redundant slug columns, metadata JSON on expand, and a
timeline that shows routing nodes rather than meaningful agent activity.
This is developer debugging output, not a user experience.

The traces page needs to be redesigned around the user's mental model:
"I submitted a work item — show me what happened to it from start to
finish, what each agent did, what was produced, and where to find the
output."

## What the user wants to see

For a selected work item:

1. **Execution timeline** — intake → 5 Whys → planning → design validation
   → task execution → code validation → archival. Each phase as a clear
   step with duration, cost, and outcome.

2. **Agent activity per phase** — which agent ran, what model was used,
   what the agent read/wrote/executed. Not raw tool_use events but
   summarized: "Read 5 files, edited 2, ran 8 bash commands, committed."

3. **Prompts and responses** — accessible on demand (click to expand),
   not shown by default. The full prompt sent to each agent and the
   response received.

4. **Output artifacts** — links to design doc, plan YAML, validation
   results, worker output logs, git commits. Same as the item page
   artifacts section but in context of the execution flow.

5. **Technical trace data** — available via a "Show raw trace" toggle
   for debugging, but not the default view.

## Design competition

Run a design competition with 3 different approaches:

1. **Vertical timeline** — each phase is a card in a vertical scroll,
   expandable to show agent details and artifacts.

2. **Tabbed phases** — one tab per pipeline phase (Intake, Plan, Execute,
   Validate), each showing the relevant agent activity.

3. **Swimlane diagram** — horizontal lanes per agent type (intake, planner,
   coder, validator) with time flowing left to right, showing what each
   agent did and when.

Use the frontend-design skill to produce mockups for each approach.
Have the user select the winner before implementing.

## Acceptance Criteria

- Can the user select a work item and see its full execution history
  on one page? YES = pass, NO = fail
- Is each pipeline phase clearly labeled with duration, cost, and
  outcome? YES = pass, NO = fail
- Can the user access prompts and raw tool calls without them being
  shown by default? YES = pass, NO = fail
- Are output artifacts (design doc, validation results, commits) linked
  from the execution view? YES = pass, NO = fail
- Is the raw LangSmith trace data accessible via a toggle but not the
  default view? YES = pass, NO = fail

## LangSmith Trace: c300a1be-4cf6-4db5-95c2-589d3df11338


## 5 Whys Analysis

Title: Redesign traces page from raw LangSmith data to item-centric execution narrative
Clarity: 4
5 Whys:

1. **Why is the current traces page inadequate?** Because it displays raw LangSmith trace data with developer-focused details (routing nodes, tool_use events, metadata JSON) rather than a user-friendly view that shows what actually happened to a work item from intake to archival.

2. **Why do users need a different representation of that same data?** Because the raw traces don't map to the user's mental model—users think "I submitted work, show me what happened to it," not "show me all the internal tool calls and routing decisions."

3. **Why is mapping data to user mental models critical?** Because users need to verify that work was processed correctly at each stage, and raw technical data obscures the operational outcomes—"read 5 files" is meaningful, but a list of 47 LangSmith tool_use events is not.

4. **Why does the user need to verify work at each stage?** Because work items flow through multiple agents (intake → planning → execution → validation → archival), and users need confidence that each agent completed its responsibilities and can locate the outputs (design docs, validation results, commits, logs).

5. **Why is locating outputs essential?** Because without clear traceability linking each phase, agent activity, and resulting artifact, users cannot prove work was completed correctly, debug failures, or retrieve the information they need to act on it next.

Root Need: Users need transparent traceability of how their work items flow through the multi-agent system—which agent processed each phase, what each agent actually did, how long it took, and where to find the results—presented in language that matches their operational mental model of the work.

Summary: The traces page must become a phase-by-phase execution narrative with agent activity summaries and artifact links, replacing raw technical trace data as the primary view.
