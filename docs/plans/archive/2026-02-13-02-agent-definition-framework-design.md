# Agent Definition Framework - Design Document

> **For Claude:** REQUIRED SUB-SKILL: Use the implement skill to execute this plan task-by-task.

**Goal:** Create the foundational infrastructure for specialized agents so tasks in a plan can specify which agent type executes them, giving Claude focused context for each task type.

**Architecture:** Each agent is a markdown file with YAML frontmatter in .claude/agents/. The orchestrator reads the agent file, parses its frontmatter (name, description, tools, model), and prepends the full markdown content to the task prompt before spawning Claude. An optional "agent" field on YAML tasks selects the agent explicitly; when absent, inference rules auto-select based on task description keywords.

**Tech Stack:** Python 3 (plan-orchestrator.py, auto-pipeline.py), YAML (plan schema, config), Markdown with YAML frontmatter (agent definitions)

---

## Architecture Overview

### Agent File Format

Each agent lives in .claude/agents/ as a markdown file with YAML frontmatter:

    ---
    name: coder
    description: Implementation specialist for coding tasks
    tools:
      - Read
      - Edit
      - Write
      - Bash
      - Grep
      - Glob
    model: sonnet
    ---

    # Coder Agent

    You are an implementation specialist...

The frontmatter fields:
- **name** (required): Unique identifier matching the filename without extension
- **description** (required): When to use this agent (also used by inference)
- **tools** (optional): Allowed tools (informational for prompt guidance, not enforced)
- **model** (optional): Preferred model (sonnet, haiku, opus) - informational, not enforced by CLI

The markdown body is the agent's role prompt, guidelines, and checklists.

### Orchestrator Integration

The integration point is build_claude_prompt() in plan-orchestrator.py (line 1085). When a task has an agent field (explicit or inferred), the orchestrator:

1. Resolves the agent file path from AGENTS_DIR config
2. Reads the .md file
3. Parses YAML frontmatter to extract metadata
4. Prepends the full agent content (frontmatter + body) to the prompt
5. Logs which agent is being used (in verbose mode)

The modified prompt structure becomes:

    [Agent Definition (full markdown with frontmatter)]
    ---
    [Subagent Context (if parallel)]
    [Task Details and Instructions (existing prompt)]

### Agent Inference

When no explicit agent field is set on a task, the orchestrator infers the agent:

- Task description contains "verify", "review", "check", "validate", "regression" -> code-reviewer
- Default -> coder

Inference is a simple keyword scan. The function returns None if no agents directory exists (backward compatible with projects that have not adopted agents).

### Config Changes

New field in orchestrator-config.yaml:

    # Directory containing agent definition files
    # agents_dir: ".claude/agents/"

Both scripts load this via _config.get("agents_dir", DEFAULT_AGENTS_DIR).

### Plan Creation Template Update

The PLAN_CREATION_PROMPT_TEMPLATE in auto-pipeline.py is updated to:
1. Tell the plan creator that an agent field is available on tasks
2. List available agents by scanning the agents directory
3. Instruct it to set agent: coder or agent: code-reviewer where appropriate

---

## Key Files

### New Files

| File | Purpose |
|------|---------|
| .claude/agents/coder.md | Implementation specialist agent definition |
| .claude/agents/code-reviewer.md | Read-only coding standards reviewer agent |

### Modified Files

| File | Change |
|------|--------|
| scripts/plan-orchestrator.py | Add agent loading, inference, prompt injection |
| scripts/auto-pipeline.py | Add AGENTS_DIR config, update plan creation template |
| .claude/orchestrator-config.yaml | Add agents_dir documented field |

---

## Design Decisions

1. **Agent content is prepended to the prompt, not passed via --agents flag.** The Claude CLI's --agents flag is designed for Claude Code's subagent system, not for our custom orchestrator. Prepending to the prompt is simpler, works today, and gives us full control.

2. **Frontmatter parsing uses a simple regex split, not a YAML library.** Agent files use the standard --- delimited frontmatter. We split on the second ---, parse the first part as YAML, and treat the rest as the body. This avoids adding a frontmatter parsing dependency.

3. **Tool restrictions and model selection are informational only.** The orchestrator does not enforce them. The agent's prompt text instructs Claude which tools to use. Model selection would require the Claude CLI to support a --model flag, which it does not. These fields are documented in the frontmatter for future enforcement and for human readers.

4. **Inference is opt-in: returns None when no agents dir exists.** Projects that have not created .claude/agents/ get exactly the same behavior as before. No agent content is injected.

5. **Two initial agents (coder, code-reviewer) are minimal and focused.** They prove the framework works without overbuilding. The on-hold specialized-agent-architecture document describes the full agent hierarchy for future phases.
