# Design: Least-Privilege Agent Sandboxing

## Reference
- Backlog item: docs/feature-backlog/16-least-privilege-agent-sandboxing.md
- Date: 2026-02-18

## Architecture Overview

Replace `--dangerously-skip-permissions` with per-agent permission profiles
that use the Claude CLI's built-in `--allowedTools` flag and project-directory
scoping via `--add-dir`.

```
  Agent Definition (.md)          Permission Profile (dict)
  ┌──────────────────────┐       ┌─────────────────────────────────┐
  │ tools:               │──────>│ allowed_tools: ["Read","Grep"]  │
  │   - Read             │       │ bash_policy: "read_only"        │
  │   - Grep             │       │ project_scoped: true            │
  │   - Glob             │       └──────────┬──────────────────────┘
  └──────────────────────┘                  │
                                            v
                              build_permission_flags()
                                            │
                              ┌─────────────v─────────────┐
                              │ --allowedTools Read Grep   │
                              │   Glob "Bash(read:*)"     │
                              │ --add-dir /project/root   │
                              └───────────────────────────┘
```

## Permission Profiles

Four profiles, mapped to agent types:

### 1. READ_ONLY
Agents: code-reviewer, systems-designer, ux-reviewer, spec-verifier,
        e2e-analyzer, qa-auditor, code-explorer, code-architect
- Tools: Read, Grep, Glob, Bash (read-only commands)
- Bash policy: Limited to read-only commands (no file mutations)
- File access: Project directory only

### 2. WRITE
Agents: coder, frontend-coder
- Tools: Read, Grep, Glob, Write, Edit, Bash, NotebookEdit
- Bash policy: Build/test commands (pnpm, pytest, tsc, git add, git commit)
- File access: Project directory only

### 3. VERIFICATION
Agents: validator, issue-verifier
- Tools: Read, Grep, Glob, Bash (for running tests)
- No Write or Edit
- Bash policy: Test/build commands only
- File access: Project directory only

### 4. DESIGN
Agents: ux-designer, ux-implementer, planner
- Tools: Read, Grep, Glob, Write (for design docs only)
- Bash policy: Exploration commands only
- File access: Project directory only

## Key Design Decisions

### Use --allowedTools instead of --tools
The `--allowedTools` flag provides a whitelist of permitted tools. When combined
with the absence of `--dangerously-skip-permissions`, the CLI enforces that only
listed tools are available. The `--tools` flag restricts what tools are loaded
but does not enforce permission checking -- `--allowedTools` does both.

### Bash tool scoping via pattern syntax
Claude CLI supports tool patterns like `Bash(git:*)` or `Bash(pytest:*)`.
For read-only agents, we use a restrictive pattern. For write agents, we
allow build/test commands. This provides fine-grained control without
needing to enumerate every allowed command.

### Agent definition as source of truth
Each agent .md file already declares its tools in the YAML frontmatter.
The permission system reads these declarations and maps them to CLI flags.
If an agent file declares `tools: [Read, Grep, Glob]`, the permission
builder generates `--allowedTools Read Grep Glob`.

### Project-directory scoping
All agent launches add `--add-dir <project_root>` to limit file access to
the project directory. This is combined with `--permission-mode default` (not
bypassPermissions) to enforce standard permission checks.

### Backward compatibility
A `SANDBOX_ENABLED` constant (default: True) controls whether sandboxing is
active. When disabled, the system falls back to `--dangerously-skip-permissions`
for debugging. This is configured via environment variable
`ORCHESTRATOR_SANDBOX_ENABLED=false`.

## Files to Create/Modify

### New files
- None (all changes in existing files)

### Modified files
- `scripts/plan-orchestrator.py`:
  - Add AGENT_PERMISSION_PROFILES dict mapping agent names to profiles
  - Add `build_permission_flags(agent_name)` function
  - Modify `run_claude_task()` to use permission flags
  - Modify `run_parallel_task()` to use permission flags
  - Modify `send_notification()` to use permission flags
  - Modify `SlackQuestionHandler._call_claude_print()` to use permission flags
  - Add logging for which profile is applied

- `scripts/auto-pipeline.py`:
  - Add similar permission profile support
  - Modify 3 Claude launch points (idea intake, plan creation, verification)
  - Each pipeline function maps to an appropriate profile

- `tests/test_plan_orchestrator.py`:
  - Add tests for `build_permission_flags()` function
  - Add tests for profile selection logic
  - Add tests for sandbox enable/disable toggle

## Acceptance Criteria Mapping

1. Each agent type has a defined, documented permission profile -> AGENT_PERMISSION_PROFILES dict
2. Agents cannot access files outside the project directory -> --add-dir flag
3. Agents cannot use tools beyond their permission profile -> --allowedTools whitelist
4. Permission profile selection is logged -> verbose_log() calls
5. Existing pipeline functionality is unaffected -> all current tests pass
