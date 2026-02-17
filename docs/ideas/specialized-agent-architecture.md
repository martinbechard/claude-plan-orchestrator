# Feature: Specialized Agent Architecture for Orchestrator

## Status: Open

## Priority: High (reduces prompt bloat, improves task quality, prevents recurring defect classes)

## Summary

Replace the current "one generic Claude session per task" model with a specialized agent
architecture where each task is executed by a role-specific agent. Each agent carries focused
knowledge (coding rules, verification checklists, design criteria) without needing the full
project CLAUDE.md in every prompt. The orchestrator selects the appropriate agent based on
the task type, reducing prompt size while improving output quality.

## Problem Statement

Today, every task spawned by the orchestrator runs as a generic Claude session that reads
the same CODING-RULES.md and whatever context the implement skill provides. This has three
problems:

1. **Prompt bloat**: Every session receives all rules, even when most are irrelevant to the
   task (a verifier doesn't need coding style rules; a coder doesn't need verification
   checklists).

2. **Missing specialized knowledge**: A generic coder session doesn't know to validate UI
   changes against functional specs, or to check that fallback data isn't being shown when
   real data is unavailable. These lessons are learned the hard way and added to CLAUDE.md
   as band-aids, growing the prompt further.

3. **No post-implementation verification**: The orchestrator trusts that a task succeeded
   based on exit status and a status file. There is no independent verification that the
   change actually satisfies the original requirement or matches the functional spec.

## Proposed Agent Architecture

### Agent Hierarchy

```
Auto-Pipeline
  |
  v
Orchestrator
  |
  +-- Coder Agent (implementation tasks)
  |     - Reads: CODING-RULES.md, design doc, relevant source files
  |     - Focus: type safety, modularity, naming, minimal changes
  |     - For new features with UI: dispatches Design Team
  |     - Anti-patterns: no over-engineering, no fake data, commit frequently
  |
  +-- Validator Agent (post-task verification, dispatches sub-agents)
  |     |
  |     +-- Issue Verifier
  |     |     - For defect fixes: independently verifies the defect is resolved
  |     |     - Reads the original defect file, checks the fix, runs targeted tests
  |     |     - Produces a PASS/FAIL verdict with evidence
  |     |
  |     +-- Functional Spec Verifier
  |     |     - For UI changes: validates placement and behavior against specs
  |     |     - Reads the functional spec for the affected page
  |     |     - Checks that new/moved components are in the correct location
  |     |     - Checks that data display is honest (no fallback data masquerading)
  |     |
  |     +-- UX Review Agent
  |     |     - For UI changes: evaluates design quality and usability
  |     |     - Reads the rendered page (via screenshot or accessibility tree)
  |     |     - Checks: responsive layout, accessibility, visual hierarchy
  |     |     - Checks: interaction patterns, error states, loading states
  |     |     - Produces design quality score with specific improvement suggestions
  |     |
  |     +-- Code Quality Reviewer
  |           - For all code changes: checks coding standards compliance
  |           - Reads CODING-RULES.md and changed files
  |           - Checks: naming, types, file size, coupling, error handling
  |           - Checks: no unnecessary additions, no removed functionality
  |           - Produces findings list with severity ratings
  |
  +-- Design Team (dispatched for new features, especially with UI)
  |     |
  |     +-- Systems Design Agent
  |     |     - Focus: architecture, data models, API design, service boundaries
  |     |     - Produces: TypeScript interfaces, component hierarchy, data flow
  |     |     - Evaluates: scalability, maintainability, integration with existing code
  |     |
  |     +-- UX Designer Agent
  |           - Focus: visual layout, interaction patterns, user workflow
  |           - Produces: ASCII wireframes, component specs, state diagrams
  |           - Evaluates: clarity, mobile UX, accessibility, consistency
  |
  +-- Planner Agent (design-to-implementation bridge)
        - Reads winning design and creates implementation phases
        - Follows the mandatory change workflow order
        - Produces valid YAML task sections with proper dependencies
        - Sets plan_modified: true for orchestrator reload
```

### Agent Definitions

Each agent is a markdown file in `.claude/agents/` with:
- **Role description**: What this agent does and doesn't do
- **Knowledge subset**: Which rules from CODING-RULES.md are relevant
- **Checklist**: Step-by-step verification items specific to the role
- **Tool restrictions**: What tools the agent can use (validators are read-only)
- **Output format**: What the agent must produce (verdict, score, findings list)

### Agent Selection Logic

The orchestrator determines which agent to use based on task metadata:

```yaml
# Explicit agent selection in YAML
- id: '3.1'
  agent: coder
  description: Implement the user search component

# Or inferred from task context
- id: '3.1'
  agent: auto  # Orchestrator infers from description keywords
```

Inference rules:
- Task description contains "verify", "validate", "check" -> Validator Agent
- Task description contains "design", "wireframe", "layout" -> Design Team
- Task description contains "extend plan", "create tasks" -> Planner Agent
- Default -> Coder Agent

### Orchestrator Changes

The orchestrator needs these modifications:

1. **Agent prompt injection**: When spawning Claude for a task, prepend the agent's
   markdown content as a system-level instruction before the task prompt.

2. **Post-task validation hook**: After a Coder Agent completes a task, optionally
   spawn a Validator Agent to independently verify the result. This replaces the
   current "trust the status file" approach.

3. **Design team dispatch**: When the Coder Agent encounters a new feature task
   marked for design competition, it triggers the existing Phase 0 pattern but
   using the specialized Design Team agents instead of generic sessions.

4. **Agent field in YAML**: New optional field `agent` on task definitions.
   When absent, use inference rules. When present, use the specified agent.

5. **Validation configuration**: New fields in plan meta to control validation:
   ```yaml
   meta:
     validation:
       enabled: true
       run_after: [coder]  # Which agents trigger post-validation
       validators: [issue_verifier, spec_verifier, code_reviewer]
       skip_for_phases: [phase-0]  # Don't validate design generation
   ```

### Generic SE/Quality Rules Extracted from Project Experience

These rules were identified from real production issues and should be embedded in the
appropriate agent definitions:

**For Coder Agent:**
- Never use `any` type; create proper types for all data structures
- Don't use literal constants; use manifest constants at file top
- Large files (500+ lines) are a code smell; split into modules
- Never defer integration; if you create a component, wire it in immediately
- Commit frequently; uncommitted work is lost when the session ends
- Don't add features or abstractions beyond what was requested
- When a value is NULL/missing, show that state honestly; never invent fallbacks
- Don't hardcode lists that duplicate a registry or source of truth
- Follow the mandatory change workflow order: spec -> docs -> code -> tests
- Read CODING-RULES.md before generating any code

**For Functional Spec Verifier:**
- Before any UI change, read the functional spec for the affected page
- Verify component placement matches the user workflow (config controls belong
  on config pages, not overview pages)
- Check that data display is honest: no fallback data from different sources
- Check that no existing functionality was removed without explicit permission
- Verify the mandatory change workflow was followed (spec updated before code)

**For Issue Verifier:**
- Read the original defect/feature description
- Check each acceptance criterion independently
- Run targeted tests (unit + E2E) for the specific fix
- Build passing does NOT mean the fix works; verify the actual behavior
- Produce PASS/FAIL with specific evidence for each criterion
- For defects: verify the root cause was addressed, not just symptoms

**For UX Review Agent:**
- Check mobile and desktop layouts
- Verify accessibility (ARIA labels, keyboard navigation, color contrast)
- Check loading states, error states, and empty states
- Verify visual hierarchy and information density
- Check that the UI uses the project's existing component library
- Verify notification/feedback uses the centralized toast system, not inline divs

**For Code Quality Reviewer:**
- Verify naming conventions (PascalCase classes, camelCase functions, etc.)
- Check file organization matches project conventions
- Verify no circular dependencies introduced
- Check for type safety violations (any, type assertions)
- Verify imports are organized (external -> project -> relative)
- Check for AI-specific anti-patterns: over-engineering, removed functionality,
  fake data, deferred integration

**For Systems Design Agent:**
- Produce TypeScript interfaces for all components and data flows
- Consider integration with existing code (don't reinvent existing patterns)
- Evaluate trade-offs: simplicity vs flexibility, performance vs maintainability
- Include edge cases and error scenarios in the design

**For UX Designer Agent:**
- Produce ASCII wireframes for all states (normal, loading, error, empty)
- Consider mobile-first design
- Use the project's existing design system / component library
- Include interaction specifications (hover, click, drag, keyboard)

## Validation Flow

For each implementation task, the flow becomes:

```
1. Orchestrator selects Coder Agent for task
2. Coder Agent implements the change
3. Coder Agent writes status file (completed/failed)
4. IF validation enabled AND task completed:
   a. Orchestrator spawns Validator Agent
   b. Validator dispatches relevant sub-agents:
      - Code Quality Reviewer (always)
      - Issue Verifier (if fixing a defect)
      - Functional Spec Verifier (if UI changed)
      - UX Review Agent (if UI changed)
   c. Each sub-agent produces findings
   d. Validator aggregates findings into verdict:
      - PASS: No blocking issues
      - WARN: Minor issues noted but not blocking
      - FAIL: Blocking issues found, task needs rework
5. IF verdict is FAIL:
   - Orchestrator marks task as failed with validation findings
   - Task gets retried with findings appended to prompt
6. IF verdict is PASS/WARN:
   - Orchestrator marks task as completed
   - Warnings are logged for human review
```

This is the same verification cycle pattern already proven with the auto-pipeline
(Plan -> Execute -> Verify -> Archive/Retry), now applied at the individual task level.

## Design Competition Enhancement

The existing Phase 0 design competition pattern gets enhanced:

- **Design Generator tasks**: Use the specialized Systems Design Agent or UX Designer
  Agent instead of generic Claude sessions, producing more focused designs
- **Judge task**: Gets explicit scoring criteria from the agent definition, ensuring
  consistent evaluation across all competitions
- **Agent team variant**: For features requiring both architectural and UX design,
  the Coder Agent dispatches a Systems Design Agent + UX Designer Agent as a team
  that can discuss trade-offs before producing a joint design

## Implementation Plan

### Phase 1: Agent Definition Framework
1. Create `.claude/agents/` directory structure in the orchestrator template
2. Define the agent markdown format (frontmatter + role prompt + checklist)
3. Create the Coder Agent definition (`coder.md`)
4. Create the Code Quality Reviewer definition (`code-reviewer.md`)
5. Modify orchestrator to read and inject agent prompts when spawning Claude

### Phase 2: Validation Pipeline
6. Create the Validator Agent definition (`validator.md`)
7. Create the Issue Verifier definition (`issue-verifier.md`)
8. Create the Functional Spec Verifier definition (`spec-verifier.md`)
9. Add post-task validation hook to orchestrator
10. Add `validation` config to plan meta schema
11. Implement PASS/WARN/FAIL verdict aggregation
12. Implement retry-with-findings for FAIL verdicts

### Phase 3: Design Agents
13. Create the Systems Design Agent definition (`systems-designer.md`)
14. Create the UX Designer Agent definition (`ux-designer.md`)
15. Create the Planner Agent definition (`planner.md`)
16. Update Phase 0 competition template to use specialized design agents
17. Add agent team dispatch support for cross-disciplinary design

### Phase 4: Orchestrator Integration
18. Add `agent` field to YAML task schema
19. Implement agent inference rules (auto-selection from task description)
20. Update implement skill to document agent selection
21. Add validation flow documentation
22. Update README and narrative docs

### Phase 5: Testing and Hardening
23. Test coder agent on a simple feature plan
24. Test validation pipeline on a known-defective implementation
25. Test design competition with specialized agents
26. Performance testing: measure token savings from focused prompts
27. Document lessons learned

## Cost Analysis

**Current cost per task**: Full CLAUDE.md + CODING-RULES.md + design doc = large prompt
**Proposed cost per task**: Focused agent prompt + relevant rules subset = smaller prompt

Estimated token savings per task: 30-50% reduction in system prompt tokens.

The validation step adds cost (one extra Claude invocation per implementation task), but
this is offset by:
- Catching defects before they compound (the model-config-on-wrong-page defect cost
  multiple sessions to identify and will cost more to fix)
- Reducing retry cycles (validation catches issues the coder missed)
- Smaller prompts per invocation

## Plugin Packaging

### Why a Plugin

The orchestrator currently distributes via manual file copying:

```bash
cp -r claude-plan-orchestrator/.claude/ /path/to/your/project/
cp -r claude-plan-orchestrator/scripts/ /path/to/your/project/
```

This has problems: no version management, no update mechanism, no dependency tracking,
and users must remember which files to copy. The Claude Code plugin system solves all
of these. Packaging the orchestrator + agents as a plugin means:

- **One-command install**: `claude plugin install plan-orchestrator`
- **Automatic updates**: `claude plugin update plan-orchestrator`
- **Version management**: Semver in plugin.json tracks releases
- **Automatic agent discovery**: Claude invokes agents based on their description fields
- **Namespace isolation**: All skills/commands are prefixed (e.g., `/plan-orchestrator:implement`)
- **Distribution via marketplace**: npm, GitHub, or custom team marketplace

### Plugin Directory Structure

```
plan-orchestrator/
  .claude-plugin/
    plugin.json                    # Plugin manifest
  agents/
    coder.md                       # Implementation specialist
    validator.md                   # Post-task verification coordinator
    issue-verifier.md              # Defect fix verification
    spec-verifier.md               # Functional spec compliance
    ux-reviewer.md                 # UI/UX quality review
    code-reviewer.md               # Coding standards compliance
    systems-designer.md            # Architecture design generation
    ux-designer.md                 # Visual/interaction design generation
    planner.md                     # Design-to-YAML plan bridge
  skills/
    implement/
      SKILL.md                     # Main implement skill (current SKILL.md)
    coding-rules/
      SKILL.md                     # CODING-RULES.md as a skill
      CODING-RULES.md              # Full rules (supporting file)
  commands/
    implement.md                   # /plan-orchestrator:implement command
  hooks/
    hooks.json                     # Event handlers for validation flow
  scripts/
    plan-orchestrator.py           # Orchestrator script
    auto-pipeline.py               # Auto-pipeline daemon
    validate-task.sh               # Post-task validation hook script
  README.md
  CHANGELOG.md
```

### Plugin Manifest

```json
{
  "name": "plan-orchestrator",
  "version": "2.0.0",
  "description": "Automated multi-step plan execution with specialized agents, design competitions, and post-task validation",
  "author": {
    "name": "Martin Bechard",
    "email": "martin.bechard@DevConsult.ca"
  },
  "repository": "https://github.com/martinbechard/claude-plan-orchestrator",
  "license": "MIT",
  "keywords": ["orchestrator", "pipeline", "agents", "automation", "code-quality"]
}
```

### Agent Definitions as Plugin Agents

Each agent uses YAML frontmatter following the Claude Code subagent specification.
Key frontmatter fields available:

| Field | Purpose | Example |
|-------|---------|---------|
| `name` | Unique identifier | `coder` |
| `description` | When Claude should delegate to this agent | "Implementation specialist. Use for coding tasks." |
| `tools` | Allowed tools (allowlist) | `Read, Edit, Write, Bash, Grep, Glob` |
| `disallowedTools` | Denied tools (denylist) | `Write, Edit` (for read-only validators) |
| `model` | Model selection | `sonnet` for coding, `haiku` for quick checks, `opus` for design |
| `permissionMode` | Permission behavior | `plan` for read-only, `acceptEdits` for coders |
| `skills` | Preloaded skills | `[coding-rules, implement]` |
| `memory` | Persistent cross-session learning | `user` or `project` |
| `hooks` | Agent-scoped event handlers | PreToolUse validation scripts |
| `maxTurns` | Turn limit for agent | `50` |

#### Example: Coder Agent (agents/coder.md)

```markdown
---
name: coder
description: >
  Implementation specialist for coding tasks. Use proactively when implementing
  features, fixing defects, writing code, or modifying existing source files.
  Follows CODING-RULES.md, validates against specs, and commits frequently.
tools: Read, Edit, Write, Bash, Grep, Glob
model: sonnet
skills:
  - coding-rules
memory: project
---

You are an implementation specialist. Your job is to write high-quality code
that follows the project's coding standards and design specifications.

## Before Writing Code

1. Read CODING-RULES.md (preloaded via skill)
2. Read the design document referenced in the task
3. Read existing code in the files you will modify
4. For UI changes: read the functional spec for the affected page

## Coding Standards (Summary)

- Never use any type; create proper typed interfaces
- Use manifest constants, not literal values
- Files > 500 lines must be split into modules
- Follow existing patterns in the codebase
- Commit after each meaningful unit of work

## Anti-Patterns to Avoid

- No over-engineering beyond what was requested
- No fake fallback data when real data is unavailable
- No deferred integration; wire components in immediately
- No removal of existing functionality without explicit permission
- No hardcoded lists that duplicate a registry or source of truth

## Output Protocol

Write task-status.json when done:
{task_id, status: "completed"|"failed", message, timestamp, plan_modified}
```

#### Example: Spec Verifier (agents/spec-verifier.md)

```markdown
---
name: spec-verifier
description: >
  Functional specification verifier. Use after UI changes to validate that
  component placement, data display, and user workflow match the spec.
  Read-only: does not modify code.
tools: Read, Grep, Glob
model: haiku
permissionMode: plan
---

You are a functional specification verifier. Your job is to independently
verify that code changes match the project's functional specifications.

## Verification Checklist

1. Read the functional spec for every page affected by the changes
2. For each UI component added or moved:
   - Does it appear on the correct page per the spec?
   - Is it in the correct section/position within the page?
   - Does it match the workflow described in the spec?
3. For each data display:
   - Is real data shown when available?
   - When data is unavailable, does it show "--" or "Not configured"?
   - Is there any fallback to data from a different source? (FAIL if yes)
4. For removed components: was removal explicitly requested?

## Output Format

Produce a structured verdict:

VERDICT: PASS | WARN | FAIL

FINDINGS:
- [PASS|WARN|FAIL] Finding description with specific file:line references
- ...

EVIDENCE:
- Spec reference: [page/section in functional spec]
- Code reference: [file:line in source]
```

#### Example: UX Designer Agent (agents/ux-designer.md)

```markdown
---
name: ux-designer
description: >
  UX/UI design specialist for generating visual and interaction designs.
  Use during Phase 0 design competitions or when evaluating UI approaches.
  Produces ASCII wireframes, component specs, and state diagrams.
tools: Read, Grep, Glob, Write
model: opus
---

You are a UX/UI design specialist. Your job is to create detailed,
implementable designs for user interfaces.

## Design Deliverables

Every design document must include:

1. ASCII wireframes for all states (normal, loading, error, empty)
2. Component hierarchy with TypeScript interfaces
3. Interaction specifications (hover, click, drag, keyboard)
4. Mobile and desktop variants
5. Edge case handling (long text, missing data, permissions)

## Design Principles

- Mobile-first responsive design
- Use the project's existing component library (check for existing components)
- Minimize cognitive load; progressive disclosure for complex features
- Accessible: ARIA labels, keyboard navigation, sufficient contrast
- Use the project's existing notification/toast system for feedback

## Evaluation Criteria (for competitions)

Score each design 1-10 on:
1. Clarity: Is the purpose immediately obvious?
2. Space Efficiency: Does it use screen real estate well?
3. Consistency: Does it match existing UI patterns?
4. Implementation Feasibility: How much work to build?
5. Discoverability: Can users find features without documentation?
```

### Hook Configuration for Validation Flow

The plugin's `hooks/hooks.json` enables automatic post-task validation:

```json
{
  "hooks": {
    "SubagentStop": [
      {
        "matcher": "coder",
        "hooks": [
          {
            "type": "prompt",
            "prompt": "The coder agent just completed a task. Check task-status.json. If status is 'completed', invoke the validator agent to verify the changes. If the task modified UI files (.tsx), also invoke the spec-verifier and ux-reviewer agents."
          }
        ]
      }
    ],
    "TaskCompleted": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/scripts/validate-task.sh"
          }
        ]
      }
    ]
  }
}
```

### Persistent Memory for Learning

Agents with `memory: project` accumulate knowledge in `.claude/agent-memory/<agent-name>/`:

- **Coder memory**: Stores codebase patterns, file locations, architecture decisions
  discovered during implementation. Future coding sessions benefit from this institutional
  knowledge without re-exploring.

- **Validator memory**: Stores recurring defect patterns, common spec violations, and
  false positive suppressions. Over time, validation becomes more accurate as the agents
  learn what to look for in this specific project.

- **Designer memory**: Stores design decisions, winning patterns from competitions, and
  user feedback on previous designs. Future competitions start with better context.

### Skills as Rule Subsets

Instead of each agent reading the full CODING-RULES.md, rules are packaged as
preloadable skills that agents reference in their `skills` frontmatter:

```
skills/
  coding-rules/
    SKILL.md              # Entry point: summary + navigation
    CODING-RULES.md       # Full rules (supporting file, loaded on demand)
    coder-subset.md       # Rules relevant to implementation
    reviewer-subset.md    # Rules relevant to code review
    design-subset.md      # Rules relevant to design generation
```

The `SKILL.md` file provides a concise overview, and supporting files contain
detailed rules that agents load only when needed. This is the progressive disclosure
pattern recommended by Claude Code's skill documentation.

### Distribution Strategy

Three distribution tiers:

1. **GitHub repository** (current): Clone and copy files manually. Still works.

2. **Plugin marketplace**: Create a `marketplace.json` in the repo root:
   ```json
   {
     "plugins": [
       {
         "name": "plan-orchestrator",
         "description": "Multi-step plan execution with specialized agents",
         "source": "./",
         "version": "2.0.0"
       }
     ]
   }
   ```
   Teams configure the marketplace URL in their project settings:
   ```json
   {
     "pluginMarketplaces": ["https://github.com/martinbechard/claude-plan-orchestrator"]
   }
   ```
   Then install: `claude plugin install plan-orchestrator`

3. **npm package** (future): `npm install -g @plan-orchestrator/claude-plugin` for
   the broadest distribution, with automatic updates via `claude plugin update`.

### Migration Path from Current Structure

Existing users who copied files manually can migrate to the plugin:

1. Install the plugin: `claude plugin install plan-orchestrator`
2. The plugin agents and skills supplement (don't replace) existing `.claude/` files
3. Remove manually-copied `.claude/agents/`, `.claude/skills/implement/` once verified
4. Keep project-specific agents in `.claude/agents/` (they take priority over plugin agents)
5. The orchestrator scripts in `scripts/` continue to work alongside the plugin

### Integration Between Orchestrator and Plugin Agents

The orchestrator (`scripts/plan-orchestrator.py`) needs to know how to invoke plugin
agents when spawning Claude sessions. Two approaches:

**Approach A: --agents CLI flag** (recommended)
The orchestrator reads the agent markdown file and passes it via `--agents` JSON:

```python
agent_content = read_file(f".claude/agents/{agent_name}.md")
# OR from plugin: find plugin agent path
claude_cmd = f'claude --agents \'{{"agent_name": {{"prompt": "{agent_content}", ...}}}}\' ...'
```

**Approach B: Agent-aware prompting**
The orchestrator prepends "Use the {agent_name} agent for this task" to the task prompt,
relying on Claude's automatic delegation based on agent descriptions. Simpler but less
deterministic.

Approach A gives the orchestrator full control over which agent runs. Approach B is
simpler but relies on Claude's judgment. Recommend starting with A for the orchestrator
and letting B work for interactive use.

## Updated Implementation Plan

### Phase 1: Agent Definition Framework
1. Create plugin directory structure with `.claude-plugin/plugin.json`
2. Define agent markdown format using Claude Code frontmatter spec
3. Create the Coder Agent definition (`agents/coder.md`)
4. Create the Code Quality Reviewer definition (`agents/code-reviewer.md`)
5. Modify orchestrator to read agent files and inject via `--agents` flag

### Phase 2: Validation Pipeline
6. Create the Validator Agent definition (`agents/validator.md`)
7. Create the Issue Verifier definition (`agents/issue-verifier.md`)
8. Create the Functional Spec Verifier definition (`agents/spec-verifier.md`)
9. Create hooks configuration (`hooks/hooks.json`) for SubagentStop validation
10. Add `validation` config to plan meta schema
11. Implement PASS/WARN/FAIL verdict aggregation in orchestrator
12. Implement retry-with-findings for FAIL verdicts

### Phase 3: Design Agents
13. Create the Systems Design Agent definition (`agents/systems-designer.md`)
14. Create the UX Designer Agent definition (`agents/ux-designer.md`)
15. Create the Planner Agent definition (`agents/planner.md`)
16. Update Phase 0 competition template to use specialized design agents
17. Add agent team dispatch support for cross-disciplinary design

### Phase 4: Skills and Rules Packaging
18. Convert CODING-RULES.md into a skill with subsets (`skills/coding-rules/`)
19. Move implement skill into plugin structure (`skills/implement/`)
20. Create rule subset files for each agent role
21. Configure agent `skills` frontmatter to preload relevant subsets

### Phase 5: Plugin Distribution
22. Create `marketplace.json` for GitHub-based installation
23. Write plugin README with installation and usage instructions
24. Add CHANGELOG.md for version tracking
25. Test installation via `claude plugin install` from marketplace
26. Test `--plugin-dir` development workflow

### Phase 6: Orchestrator Integration
27. Add `agent` field to YAML task schema
28. Implement agent inference rules (auto-selection from task description)
29. Implement `--agents` flag injection in orchestrator spawn logic
30. Update implement skill to document agent selection
31. Add validation flow documentation

### Phase 7: Testing and Hardening
32. Test coder agent on a simple feature plan
33. Test validation pipeline on a known-defective implementation
34. Test design competition with specialized agents
35. Test plugin install/update/uninstall lifecycle
36. Performance testing: measure token savings from focused prompts
37. Document lessons learned in narrative/

## Dependencies

None. This is a standalone enhancement to the orchestrator.

## Files Affected

### Plugin Files (New)

| File | Purpose |
|------|---------|
| `.claude-plugin/plugin.json` | Plugin manifest with metadata and version |
| `agents/coder.md` | Coder Agent: implementation specialist |
| `agents/validator.md` | Validator Agent: post-task verification coordinator |
| `agents/issue-verifier.md` | Issue Verifier: defect fix verification |
| `agents/spec-verifier.md` | Spec Verifier: functional spec compliance |
| `agents/ux-reviewer.md` | UX Reviewer: UI/UX quality review |
| `agents/code-reviewer.md` | Code Reviewer: coding standards compliance |
| `agents/systems-designer.md` | Systems Designer: architecture design generation |
| `agents/ux-designer.md` | UX Designer: visual/interaction design generation |
| `agents/planner.md` | Planner: design-to-YAML plan bridge |
| `skills/implement/SKILL.md` | Implement skill (moved from .claude/skills/) |
| `skills/coding-rules/SKILL.md` | Coding rules skill entry point |
| `skills/coding-rules/CODING-RULES.md` | Full coding rules (supporting file) |
| `skills/coding-rules/coder-subset.md` | Rules subset for implementation agents |
| `skills/coding-rules/reviewer-subset.md` | Rules subset for review agents |
| `skills/coding-rules/design-subset.md` | Rules subset for design agents |
| `commands/implement.md` | /plan-orchestrator:implement command |
| `hooks/hooks.json` | SubagentStop + TaskCompleted hooks for validation |
| `scripts/validate-task.sh` | Post-task validation hook script |
| `marketplace.json` | GitHub marketplace definition |

### Existing Files (Modified)

| File | Change |
|------|--------|
| `scripts/plan-orchestrator.py` | Agent prompt injection via --agents flag, validation hook, agent inference from YAML |
| `scripts/auto-pipeline.py` | Pass agent config to orchestrator |
| `CODING-RULES.md` | Annotate rules with agent applicability tags |
| `README.md` | Document plugin installation, agent architecture, validation flow |

## References

- Claude Code Plugin Documentation: https://code.claude.com/docs/en/plugins
- Claude Code Plugin Reference: https://code.claude.com/docs/en/plugins-reference
- Claude Code Subagents Documentation: https://code.claude.com/docs/en/sub-agents
- Claude Code Skills Documentation: https://code.claude.com/docs/en/skills
- Claude Code Hooks Documentation: https://code.claude.com/docs/en/hooks
