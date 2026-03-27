# Design: UI Quality Process Lost in LangGraph Migration (#37)

## Problem

The old pipeline had a UI design competition process (3 parallel designs, judging,
then implementation) that was lost during the LangGraph migration. Web UI pages were
built without design review, resulting in inconsistent styling.

## Current State

Partial implementation already exists:

1. **Planner agent** (.claude/agents/planner.md) has a "UI Work Item Detection"
   section (lines 96-109) that instructs the planner to invoke the frontend-design
   skill and assign UI tasks to frontend-coder.
2. **Frontend-coder agent** (.claude/agents/frontend-coder.md) references
   docs/ui-style-guide.md in its "Before Writing Code" checklist.
3. **Style guide** (docs/ui-style-guide.md) exists as the canonical style reference.
4. **Coder agent** (.claude/agents/coder.md) does NOT reference the UI process or
   style guide -- a gap if a coder task touches UI files.

## Acceptance Criteria Check

- Documented UI design review process in planner or coder agent prompts?
  **PARTIAL** -- planner has it, coder does not.
- Planner invokes frontend-design skill for UI work items?
  **YES** -- line 101 of planner.md.
- Style guide exists?
  **YES** -- docs/ui-style-guide.md.

## Required Changes

### Task 1: Validate and fix gaps in agent prompts

The coder agent needs a section similar to the planner's "UI Work Item Detection"
that redirects to frontend-coder when UI files are involved, or at minimum references
the style guide. This ensures UI quality even when tasks are assigned to the generic
coder agent.

Key files to modify:
- .claude/agents/coder.md -- add UI awareness section

Key files to validate (read-only):
- .claude/agents/planner.md -- confirm UI Work Item Detection section is complete
- .claude/agents/frontend-coder.md -- confirm style guide reference
- docs/ui-style-guide.md -- confirm it covers the specific UI issues listed in the
  backlog item (pagination, empty states, table styling, card layouts, cost displays)

## Design Decisions

1. **Add to coder, not replace** -- The coder agent should know about UI conventions
   and redirect to the style guide, since some tasks may touch UI incidentally.
2. **Single task** -- Since this is a validation + gap-fix of existing work, one task
   is sufficient. The validator will check all three acceptance criteria.
