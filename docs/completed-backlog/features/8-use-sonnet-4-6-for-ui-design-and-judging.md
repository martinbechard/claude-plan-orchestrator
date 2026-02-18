# Use Sonnet 4.6 for UI design generation and design competition judging

## Status: Open

## Priority: Medium

## Summary

Sonnet 4.6 is optimized for UI/frontend design work. The orchestrator should
leverage this by:

1. Switching the ux-designer agent from opus to sonnet for design generation
2. Adding a dedicated frontend-coder agent (sonnet) for UI implementation tasks
3. Using sonnet as the judge for UI-focused design competitions, while keeping
   opus as the judge for architecture and complex system design competitions

## Current State

- ux-designer agent uses opus (overkill for visual design, slower and more expensive)
- ux-reviewer agent uses sonnet (already correct)
- No frontend-specific coding agent exists; the generic coder agent handles all implementation
- Design competition judging has no model-awareness; there is no built-in judge
  mechanism in the orchestrator — competitions are structured as YAML plan patterns
  where a planner task reads the designs

## Changes Required

### 1. Update ux-designer agent model

In .claude/agents/ux-designer.md, change model from opus to sonnet. Sonnet 4.6
produces better UI designs and is faster/cheaper. Opus remains appropriate for
systems-designer (architecture decisions require deeper reasoning).

### 2. Create frontend-coder agent

Add .claude/agents/frontend-coder.md:
- model: sonnet (4.6 excels at frontend code generation)
- Tools: Read, Edit, Write, Bash, Grep, Glob (same as coder)
- Specialized prompt for UI implementation: component structure, accessibility,
  responsive design, design system adherence
- Add FRONTEND_CODER_KEYWORDS to infer_agent_for_task() for auto-selection
  (e.g., "frontend", "component", "UI", "page", "form", "dialog", "modal")

### 3. Add judge model selection for design competitions

Add a meta.judge_model field to YAML plans that controls which model evaluates
design competition entries:

```yaml
meta:
  judge_model: sonnet   # For UI competitions
  # judge_model: opus   # For architecture competitions (default)
```

The planner agent task that reads competition results should use this model.
This requires the orchestrator to pass judge_model when building the planner
task prompt, and to override the planner's default model accordingly.

### 4. Update infer_agent_for_task

Add keyword detection for "frontend-coder" so tasks mentioning frontend, UI,
component, page, or form get routed to the specialized agent instead of the
generic coder.

## Acceptance Criteria

- ux-designer agent uses sonnet model
- New frontend-coder agent exists with sonnet model and frontend-specific prompt
- YAML plans can specify judge_model to control design competition evaluation
- infer_agent_for_task routes frontend-related tasks to frontend-coder
- Existing systems-designer remains on opus
- README agent table updated with new agent
- Tests updated for new keyword routing

## Source

Feature request based on Sonnet 4.6 release (optimized for UI design).
