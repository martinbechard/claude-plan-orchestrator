# Planner must produce validation criteria as a checklist with clear pass/fail outcomes

## Status: Open

## Priority: High

## Summary

The planner agent creates acceptance criteria as prose statements (e.g.
"/analysis displays real data after at least one worker completes"). These
are vague enough that the validator can interpret "the page renders" as
success even when the data is fake. Acceptance criteria must be written as
a checklist of specific questions with unambiguous outcomes.

## Expected Format

Each acceptance criterion in the plan YAML should be a question with a
clear binary outcome. Example:

BAD (current):
  - /analysis displays real data after at least one worker completes

GOOD (required):
  - Does the cost_tasks table contain rows with item_slug matching a real
    backlog item (not a test fixture)? YES = pass, NO = fail
  - After running one work item through the pipeline, does /analysis show
    that item's slug and a cost > $0.00? YES = pass, NO = fail
  - Is LANGCHAIN_ENDPOINT (or its replacement) set automatically during
    pipeline startup? YES = pass, NO = fail

## Fix

1. Update the planner agent prompt (.claude/agents/planner.md) to require
   acceptance criteria in question form with explicit YES/NO outcomes.
2. Add an instruction: "Each criterion must be independently verifiable by
   running a command or reading a specific value. Criteria that require
   subjective judgement or cannot be checked without manual testing must
   be flagged as WARN-only."
3. Update the validator agent prompt (.claude/agents/validator.md) to
   require that it answers each question literally and records the answer
   before determining the verdict.

## LangSmith Trace: 6ea9e605-e5ed-4708-889f-d841f7578bd6
