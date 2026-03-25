# Project setup script with interactive configuration

## Status: Open

## Priority: High

## Summary

A standalone script (`scripts/setup-project.py`) that bootstraps a new project
with claude-plan-orchestrator. It copies the required files, then launches a
Claude Code session to walk the user through configuration interactively. If the
user wants Slack integration, the setup agent uses the Chrome MCP to open the
Slack app directory, create the app, and copy the credentials — no manual
copy-pasting of tokens.

## Motivation

The current onboarding path requires reading setup-guide.md, manually copying
files, editing YAML, creating a Slack app, and wiring credentials. This is
error-prone and takes 20–30 minutes. A guided script reduces it to a single
command.

## User Experience

```
cd /path/to/my-project
python /path/to/claude-plan-orchestrator/scripts/setup-project.py
```

The script:
1. Copies files into the target project (current working directory).
2. Launches a Claude Code session that asks configuration questions one at a time
   and writes the answers into the config files.
3. If Slack is desired, opens api.slack.com/apps in Chrome via the MCP, walks
   through app creation, and writes the resulting tokens directly into
   slack.local.yaml — the user never touches a token.
4. Runs a smoke test (`python -m langgraph_pipeline --dry-run`) to confirm the
   setup is valid before exiting.

## Requirements

### Phase 1 — File scaffolding

1. Determine the source root (the directory containing this script's
   `langgraph_pipeline/` package).
2. Copy the following into the target project (skip files that already exist
   unless `--force` is passed):
   - `.claude/orchestrator-config.yaml` (from the template in this repo)
   - `.claude/agents/` directory (all agent markdown files)
   - `docs/defect-backlog/`, `docs/feature-backlog/`, `docs/analysis-backlog/`
     (empty directories with `.gitkeep`)
   - `procedure-coding-rules.md`
3. Print a summary of what was copied vs. skipped.

### Phase 2 — Claude Code interactive configuration

4. Launch `claude --print <prompt>` with a prompt that instructs the Claude
   session to:
   - Read the copied `orchestrator-config.yaml`
   - Ask the user (via `AskUserQuestion`) for:
     - Project name (written to `identity.project`)
     - Agent display names (pipeline, orchestrator, intake, qa)
     - Whether to enable LangSmith tracing (if yes, prompt for API key and
       write to `.env.local`)
     - Whether to enable the web UI (if yes, write `web.enabled: true` and
       preferred port)
     - Build command and test command for this project
   - Write all answers into `orchestrator-config.yaml`
   - Ask whether the user wants Slack integration

5. If Slack integration is desired, proceed to Phase 3. Otherwise, skip to
   Phase 4.

### Phase 3 — Slack setup via Chrome MCP

6. The Claude Code session (still running) uses the Chrome MCP to:
   a. Open `https://api.slack.com/apps` and click "Create New App" →
      "From scratch".
   b. Enter the app name (derived from `identity.project`) and select the
      workspace.
   c. Navigate to "OAuth & Permissions", add the required bot scopes:
      `channels:history`, `channels:read`, `chat:write`, `users:read`.
   d. Click "Install to Workspace" and approve.
   e. Copy the Bot User OAuth Token from the page.
   f. Navigate to "Basic Information" → copy the Signing Secret.
   g. Write both values into `slack.local.yaml`:
      ```yaml
      slack:
        bot_token: xoxb-...
        signing_secret: ...
      ```
   h. Ask the user for the Slack channel names they want to use and write
      them to `orchestrator-config.yaml` under `identity.agents`.

### Phase 4 — Smoke test

7. Run `python -m langgraph_pipeline --dry-run --no-slack` (or with
   `--no-slack` omitted if Slack was configured) and capture the output.
8. If the dry run succeeds, print a success summary with the next steps
   (how to start the pipeline, how to add backlog items).
9. If it fails, print the error and suggest running `--dry-run` manually
   with `--log-level DEBUG` to diagnose.

## Implementation Notes

- The script must be self-contained and runnable without installing any
  additional Python packages beyond what the orchestrator already requires.
- The Claude Code session in phases 2–3 should use `--dangerously-skip-permissions`
  since it needs to write config files.
- Chrome MCP availability should be checked before entering Phase 3; if not
  available, fall back to printing the manual Slack setup instructions from
  setup-guide.md.
- `--force` flag overwrites existing config files (useful for re-running setup).
- `--no-slack` flag skips Phase 3 entirely.
- `--no-claude` flag skips phases 2–3 and only does file scaffolding (for
  CI/automated environments).

## Files

- `scripts/setup-project.py` — main setup script
- `scripts/setup-templates/orchestrator-config.yaml` — clean config template
  (no project-specific values, all fields commented out with explanations)
- `tests/test_setup_project.py` — unit tests for file scaffolding logic
  (phases 2–3 are integration-only, not unit tested)
