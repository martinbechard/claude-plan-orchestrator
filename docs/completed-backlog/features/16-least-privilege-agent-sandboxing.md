# Least-Privilege Agent Sandboxing

## Status: Open

## Priority: High

## Summary

All agents launched by the pipeline (plan-orchestrator and auto-pipeline) should
run with the minimum permissions they actually need, following the principle of
least privilege. Every agent must be scoped to the project directory with no
access outside it.

## Permission Profiles

Define per-agent-type permission profiles:

**Read-only agents** (code-explorer, code-reviewer, code-architect, ux-reviewer,
spec-verifier, e2e-analyzer, systems-designer, qa-auditor):
- Tools: Read, Glob, Grep, Bash (read-only commands only)
- No Write, Edit, or NotebookEdit
- Bash restricted to non-mutating commands (no rm, mv, git push, etc.)

**Write agents** (coder, frontend-coder):
- Tools: Read, Glob, Grep, Write, Edit, Bash
- Bash scoped to build/test commands only (pnpm, pytest, tsc, etc.)
- No network commands, no system-level operations

**Verification agents** (validator, issue-verifier):
- Tools: Read, Glob, Grep, Bash (for running tests)
- No Write or Edit — verification should never modify code

**Design agents** (ux-designer, ux-implementer, planner):
- Tools: Read, Glob, Grep, Write (for design documents only)
- Bash limited to exploration commands

## Project-Directory Scoping

All agents must be constrained to the project directory. No agent should be able
to read or write files outside the project root. This prevents:
- Accidental reads of credentials or env files from other locations
- Cross-project contamination
- Prompt injection attacks that attempt to access system files

## Implementation Approach

- Use Claude Code permission modes (--permission-mode or equivalent) when
  launching subagents
- Define permission profiles as configuration in the orchestrator
- The orchestrator selects the appropriate profile based on the agent type
  specified in the plan YAML
- Log which permission profile is applied for each agent launch for auditability

## Acceptance Criteria

- Each agent type has a defined, documented permission profile
- Agents cannot access files outside the project directory
- Agents cannot use tools beyond their permission profile
- Permission profile selection is logged
- Existing pipeline functionality is unaffected (all current tests pass)
