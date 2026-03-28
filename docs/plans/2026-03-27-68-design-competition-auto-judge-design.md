# Design: Design competition auto-judge (defect 68)

## Problem

When the pipeline runs a Phase 0 design competition (3-5 mockup approaches),
the judge task currently expects a human to select the winner. This blocks the
pipeline and requires manual intervention via Slack suspension.

The pipeline should auto-judge design competitions using an Opus-level agent
that evaluates designs against acceptance criteria, selects a winner with
written rationale, and lets the pipeline proceed without blocking.

## Current architecture

- Phase 0 design competitions generate 3-5 designs in parallel (parallel_group)
- A judge task (depends_on all designs) reads the designs and selects a winner
- The judge task currently runs as a generic coder or ux-designer agent
- If the agent cannot decide autonomously, it writes status "suspended" to
  task-status.json, which triggers interrupt() and blocks for human Slack input
- The planner agent (planner.md) creates Phase 0 plans but has no awareness
  of a dedicated judge agent type

## Solution

### 1. Create a design-judge agent (.claude/agents/design-judge.md)

A new Opus-level agent specialized for evaluating competing designs:

- Reads all design documents referenced in the task description
- Reads the original requirements/acceptance criteria from the work item
- Evaluates each design on standardized criteria (usability, completeness,
  alignment with requirements, visual clarity, information hierarchy)
- Produces a scoring matrix and selects the winner
- Writes rationale and scoring to a judgment file in tmp/worker-output/
- Updates the design overview doc with the winner declaration
- Writes task-status.json with status "completed" (never suspends for
  human selection -- the pipeline proceeds automatically)
- The human can review the judgment from the worker output and override
  by editing the design doc if they disagree

### 2. Update planner agent to use design-judge for Phase 0 judge tasks

Update the planner agent definition (.claude/agents/planner.md) to:
- Reference the design-judge agent as available for judge tasks
- Instruct that Phase 0 judge tasks (task 0.6 pattern) should use
  agent: design-judge instead of coder or ux-designer

### 3. Update plan creation prompt to advertise the design-judge agent

Update the PLAN_CREATION_PROMPT in plan_creation.py to include
design-judge in the available agents list, so the planner knows to
assign it for judge tasks in new plans.

## Key files to create/modify

- .claude/agents/design-judge.md (NEW) -- Opus agent for auto-judging
- .claude/agents/planner.md -- Add design-judge to available agents
- langgraph_pipeline/pipeline/nodes/plan_creation.py -- Add design-judge
  to PLAN_CREATION_PROMPT agent list

## Design decisions

- The design-judge is a separate agent from ux-reviewer because the judge
  needs to compare multiple designs and select a winner (comparative
  evaluation), while ux-reviewer evaluates a single implemented UI
  (absolute evaluation). Different mental models, different prompts.

- The judge agent uses Opus for quality. Design evaluation requires
  nuanced comparison across multiple documents, which benefits from
  the strongest reasoning model.

- The judge writes its rationale to worker output rather than Slack
  because the judgment is a durable artifact that should be reviewable
  at any time, not just in a Slack conversation.

- Human override is implicit: the human can edit the design doc to change
  the winner declaration before the planner task (0.7) reads it and
  creates implementation phases. No explicit override mechanism is needed
  because the pipeline already supports --single-task mode for manual
  intervention at any point.

## Acceptance Criteria

- Does the pipeline auto-judge design competitions without blocking
  for human input? YES = pass, NO = fail
- Is the winning design selected by an Opus-level agent with written
  rationale? YES = pass, NO = fail
- Is the judgment saved to the item's worker output for human review?
  YES = pass, NO = fail
- Can the human override the selection if they disagree?
  YES = pass, NO = fail
