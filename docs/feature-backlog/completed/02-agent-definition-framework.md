# Agent Definition Framework

## Status: Open

## Priority: High

## Summary

Create the foundational infrastructure for specialized agents in the orchestrator.
Instead of every task running as a generic Claude session, tasks can specify which
agent type should execute them. Each agent is a markdown file with YAML frontmatter
containing role-specific instructions, tool restrictions, and checklists.

This is the core building block. The orchestrator reads the agent file and prepends
its content to the task prompt, giving Claude focused context for the task type.

## Scope

### Agent File Format

Create an .claude/agents/ directory. Each agent is a markdown file with frontmatter:

- name: unique identifier (e.g., "coder")
- description: when to use this agent
- tools: allowed tools (allowlist)
- model: which model to use (sonnet, haiku, opus)

The body contains the agent's role prompt, guidelines, and checklists.

### Initial Agent Definitions

Create two agents to prove the framework:

1. **coder.md** - Implementation specialist
   - Reads: CODING-RULES.md, design doc, relevant source files
   - Focus: type safety, modularity, naming, minimal changes
   - Anti-patterns: no over-engineering, no fake data, commit frequently

2. **code-reviewer.md** - Coding standards compliance
   - Read-only: does not modify code
   - Checks: naming, types, file size, coupling, error handling
   - Produces findings list with severity ratings

### Orchestrator Changes

1. Add optional "agent" field to YAML task schema
2. When spawning Claude for a task, if agent is specified, read the agent file
   and prepend its content to the task prompt
3. Add agent inference rules: auto-select agent based on task description keywords
   (e.g., "verify" -> code-reviewer, default -> coder)
4. New config in orchestrator-config.yaml: agents_dir (default: .claude/agents/)

### Plan Creation Template

Update PLAN_CREATION_PROMPT_TEMPLATE to tell the plan creator about available agents
and to set agent fields on tasks where appropriate.

## Verification

- Create a test plan with agent: coder on one task and agent: code-reviewer on another
- Run orchestrator in dry-run mode to verify agent prompts are injected
- Verify agent inference selects coder by default and code-reviewer for verification tasks
- Run a real test plan with both agent types to confirm end-to-end flow

## Dependencies

None. This is a standalone enhancement to the orchestrator.
