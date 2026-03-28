# Design Agents for Phase 0 Competitions - Design Document

> **For Claude:** REQUIRED SUB-SKILL: Use the implement skill to execute this plan task-by-task.

**Goal:** Create specialized design agents that replace generic Claude sessions in Phase 0 design competitions, producing more focused outputs with consistent evaluation criteria.

**Architecture:** Three new agent markdown files in .claude/agents/ (systems-designer.md, ux-designer.md, planner.md) plus orchestrator changes to route design tasks to the right agents. The existing agent framework (feature 02) handles loading and prompt injection; this feature extends it with design-specific agents and inference keywords.

**Tech Stack:** Python 3 (plan-orchestrator.py, auto-pipeline.py), YAML (plan schema), Markdown with YAML frontmatter (agent definitions)

**Dependency:** Feature 02 (Agent Definition Framework) - completed

---

## Architecture Overview

### New Agent Definitions

Three agents join the existing coder, code-reviewer, validator, and issue-verifier:

#### 1. Systems Design Agent (systems-designer.md)

Role: Architecture and data model design for Phase 0 competitions.

- **Focus:** TypeScript interfaces, component hierarchy, data flow diagrams, API boundaries, service architecture
- **Evaluates:** Scalability, maintainability, integration with existing code
- **Model:** opus (complex architectural reasoning)
- **Tools:** Read, Grep, Glob (read-only; produces design documents, not code)

Output format: A design document with sections for architecture, data models, component hierarchy, integration points, and trade-off analysis.

#### 2. UX Designer Agent (ux-designer.md)

Role: Visual and interaction design for Phase 0 competitions.

- **Focus:** ASCII wireframes, component specs, state diagrams, user workflows
- **Evaluates:** Clarity, mobile UX, accessibility, consistency with existing design system
- **Model:** opus (creative design tasks)
- **Tools:** Read, Grep, Glob (read-only; produces design specs, not code)

Output format: A design document with ASCII wireframes for all states (normal, loading, error, empty), interaction specs, and mobile/accessibility considerations.

#### 3. Planner Agent (planner.md)

Role: Bridges winning designs into implementation YAML plans.

- **Focus:** Reading the winning design and judge feedback, creating implementation phases with proper dependencies and agent assignments
- **Produces:** Valid YAML task sections appended to the plan file
- **Sets:** plan_modified: true so orchestrator reloads
- **Model:** sonnet (structured output generation)
- **Tools:** Read, Write, Bash, Grep, Glob (needs Write to modify the YAML plan)

Output format: YAML task sections following the project plan schema, with proper section/task IDs, dependencies, descriptions, and agent assignments.

### Agent Inference Updates

Expand infer_agent_for_task() in plan-orchestrator.py to recognize design-related keywords:

Current (2 outcomes):
- REVIEWER_KEYWORDS -> "code-reviewer"
- Default -> "coder"

After this feature (4 outcomes):
- REVIEWER_KEYWORDS -> "code-reviewer"
- DESIGNER_KEYWORDS (design, wireframe, layout, architecture, mockup) -> "systems-designer"
- PLANNER_KEYWORDS (extend plan, create tasks, create phases, plan sections) -> "planner"
- Default -> "coder"

The task name is also scanned (not just description) to catch short-form task names like "Generate Design 1".

Design decision: Single-word "design" maps to systems-designer by default. For UX design tasks, use the explicit agent field: agent: ux-designer. This avoids ambiguity since many architecture tasks also say "design" but mean systems design.

### Competition Template Updates

The Phase 0 template in the implement skill (SKILL.md) and the plan creation template (PLAN_CREATION_PROMPT_TEMPLATE in auto-pipeline.py) get updated to:

1. List all seven agents (coder, code-reviewer, validator, issue-verifier, systems-designer, ux-designer, planner)
2. Show how to assign agents to Phase 0 competition tasks:
   - Design generation tasks (0.1-0.5): agent: systems-designer or agent: ux-designer
   - Judge task (0.6): no agent (uses default coder inference)
   - Plan extension task (0.7): agent: planner
3. Show agent team dispatch: when a feature needs both architecture and UX, create paired tasks (one systems-designer + one ux-designer) in the same parallel_group

### Agent Team Dispatch

For features requiring both architectural and UX design, the Phase 0 template supports dispatching complementary agent pairs. This is a plan structure pattern, not orchestrator code:

    - id: '0.1'
      name: Systems Design - Approach A
      agent: systems-designer
      parallel_group: phase-0-designs
      description: |
        Create architecture design for approach A.
        OUTPUT: Write to docs/plans/feature-design-1-systems.md

    - id: '0.2'
      name: UX Design - Approach A
      agent: ux-designer
      parallel_group: phase-0-designs
      description: |
        Create UX design complementing systems design in approach A.
        OUTPUT: Write to docs/plans/feature-design-1-ux.md

The judge task (0.6) evaluates both the systems and UX designs as complementary pairs, scoring each pair holistically.

---

## Key Files

### New Files

| File | Purpose |
|------|---------|
| .claude/agents/systems-designer.md | Architecture and data model design agent |
| .claude/agents/ux-designer.md | Visual and interaction design agent |
| .claude/agents/planner.md | Design-to-implementation YAML plan bridge agent |

### Modified Files

| File | Change |
|------|--------|
| scripts/plan-orchestrator.py | Add DESIGNER_KEYWORDS, PLANNER_KEYWORDS; expand infer_agent_for_task() to scan name+description |
| scripts/auto-pipeline.py | Update PLAN_CREATION_PROMPT_TEMPLATE agent list to include all 7 agents |
| .claude/skills/implement/SKILL.md | Update Phase 0 template with agent assignments and team dispatch examples |

---

## Design Decisions

1. **Design agents are read-only (except planner).** Systems-designer and ux-designer produce design documents, not code. They use Read/Grep/Glob only. The planner needs Write and Bash to modify the YAML plan and write status.

2. **Inference defaults systems-designer for "design" keyword.** When a task description mentions "design" without specifying UX, the inference routes to systems-designer because architecture design is more common in the competition context. UX tasks should use the explicit agent: ux-designer field.

3. **Planner uses sonnet, designers use opus.** Design generation requires creative, complex reasoning (opus). Plan generation is structured output that benefits from sonnet's reliability and speed.

4. **Agent teams are a plan pattern, not orchestrator code.** The existing parallel_group mechanism handles agent teams naturally. No new orchestrator code is needed for team dispatch.

5. **Inference checks both task name and description.** The name field is also scanned for keywords since Phase 0 tasks often have short names like "Generate Design 1" where the keyword appears in the name, not the description.

6. **Keyword priority order.** REVIEWER_KEYWORDS are checked first (existing behavior), then DESIGNER_KEYWORDS, then PLANNER_KEYWORDS, then default "coder". This preserves backward compatibility.
