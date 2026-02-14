# Design Agents for Phase 0 Competitions

## Status: Open

## Priority: Low

## Summary

Create specialized design agents that replace generic Claude sessions in Phase 0
design competitions. A Systems Design Agent focuses on architecture, data models,
and API boundaries. A UX Designer Agent focuses on visual layout, interaction
patterns, and user workflow. A Planner Agent bridges designs into YAML task plans.

Using specialized agents for design competitions produces more focused outputs
with consistent evaluation criteria.

## Scope

### New Agent Definitions

Create agents in .claude/agents/:

1. **systems-designer.md** - Architecture and data model design
   - Focus: TypeScript interfaces, component hierarchy, data flow
   - Evaluates: scalability, maintainability, integration with existing code
   - Model: opus (complex reasoning needed)

2. **ux-designer.md** - Visual and interaction design
   - Focus: ASCII wireframes, component specs, state diagrams
   - Evaluates: clarity, mobile UX, accessibility, consistency
   - Model: opus (creative tasks)

3. **planner.md** - Design-to-implementation bridge
   - Reads winning design and creates implementation phases
   - Produces valid YAML task sections with proper dependencies
   - Sets plan_modified: true for orchestrator reload
   - Model: sonnet (structured output)

### Competition Template Updates

Update the Phase 0 competition template to use specialized design agents
instead of generic sessions. The orchestrator dispatches designers based
on the agent field in competition task definitions.

### Agent Team Dispatch

For features requiring both architectural and UX design, support dispatching
a Systems Design Agent + UX Designer Agent as a team that produces complementary
designs evaluated as a pair.

## Verification

- Create a test plan with a Phase 0 competition using design agents
- Verify each designer agent produces output matching its specialization
- Verify the planner agent creates valid YAML plan sections

## Dependencies

- 02-agent-definition-framework.md
