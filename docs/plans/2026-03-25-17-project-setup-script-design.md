# Design: Project Setup Script with Interactive Configuration

## Overview

A standalone `scripts/setup-project.py` script that bootstraps a new project with
claude-plan-orchestrator in a single command. It copies required files into the
target project directory, then launches a Claude Code session for interactive
configuration. If Slack is desired, the Claude Code session uses the Chrome MCP to
create the Slack app and write credentials automatically.

## Architecture

The script is entirely self-contained and divided into four phases:

1. **File scaffolding** — copies templates and agent files into the target project
2. **Claude Code interactive config** — launches `claude --print` with a structured
   prompt that uses `AskUserQuestion` to collect config values and writes them to
   `orchestrator-config.yaml` and optionally `.env.local`
3. **Slack setup via Chrome MCP** — the Claude Code session uses Chrome MCP to create
   a Slack app and write credentials to `slack.local.yaml`; falls back to manual
   instructions if Chrome MCP is unavailable
4. **Smoke test** — runs `python -m langgraph_pipeline --dry-run` and reports success
   or failure with remediation hints

## Key Files

### New files
- `scripts/setup-project.py` — main setup script (single file, no new deps)
- `scripts/setup-templates/orchestrator-config.yaml` — clean commented-out config
  template with all fields explained and no project-specific values

### New test file
- `tests/test_setup_project.py` — unit tests covering Phase 1 scaffolding logic
  (Phases 2-3 are integration-only, not unit tested)

## Design Decisions

### Source root detection
The script locates its source root by resolving the directory containing
`scripts/setup-project.py` two levels up (`Path(__file__).parent.parent`).
From there it reads `.claude/agents/`, the config template from
`scripts/setup-templates/orchestrator-config.yaml`, and `procedure-coding-rules.md`.

### Skip vs overwrite logic
Each file is skipped if it already exists in the target, unless `--force` is
passed. Backlog directories are always created; `.gitkeep` files are placed inside
only if the directory is newly created. A summary of copied vs. skipped files is
printed after scaffolding.

### Claude Code session approach
Phase 2 invokes `claude --print <prompt> --dangerously-skip-permissions` as a
subprocess and streams its output. The prompt instructs the session to read
`orchestrator-config.yaml`, gather values via `AskUserQuestion`, and write them
back. The subprocess exits when the session finishes; the setup script then reads
the return code and any error output.

### Chrome MCP availability check
Before entering Phase 3, the script checks whether the Chrome MCP server is
available (by inspecting the Claude config or running a quick probe). If not
available, it prints manual Slack setup instructions from `setup-guide.md` instead.

### CLI flags
- `--force` — overwrite existing config files
- `--no-slack` — skip Phase 3 entirely
- `--no-claude` — skip Phases 2-3, file scaffolding only (for CI/automated use)

### Unit testing scope
Only Phase 1 (file scaffolding) is unit tested via `tests/test_setup_project.py`.
Tests use `tmp_path` fixtures to create isolated source and target trees.
Phases 2-3 involve subprocess/interactive steps that are integration-only.
