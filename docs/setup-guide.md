# Setup Guide

Step-by-step instructions to get the plan orchestrator running on a new project.
Follow these steps in order.

For upgrading an existing install, see "Upgrading" at the bottom.

## Prerequisites

- Python 3.8+
- Claude Code CLI installed and authenticated
- Git
- A Slack workspace where you can create apps (for Slack integration)

## 1. Install dependencies

```bash
pip install pyyaml watchdog
```

Optional (for interactive Slack questions):
```bash
pip install slack-bolt
```

## 2. Install the plugin

```bash
claude plugin install martinbechard/claude-plan-orchestrator
```

Or for local development, clone and point Claude at it:
```bash
git clone https://github.com/martinbechard/claude-plan-orchestrator.git
claude --plugin-dir /path/to/claude-plan-orchestrator
```

## 3. Set up Slack

Run the interactive setup script. Replace "myproject" with your project name:

```bash
python scripts/setup-slack.py --prefix myproject
```

The script will:
1. Generate a Slack app manifest and open your browser
2. Walk you through creating the app and pasting tokens
3. Create four private channels: myproject-notifications, myproject-defects,
   myproject-features, myproject-questions
4. Write the config to .claude/slack.local.yaml

Channels are private by default. To create public channels instead, add --public.

To invite a human user to all channels by email:

```bash
python scripts/setup-slack.py --prefix myproject --invite-user user@example.com
```

If you already have a Slack app and just want new channels for a second project:

```bash
python scripts/setup-slack.py --prefix myproject --bot-token xoxb-your-existing-token --app-token xapp-your-existing-token
```

For CI or non-interactive contexts (no browser, no prompts):

```bash
python scripts/setup-slack.py --prefix myproject --bot-token xoxb-... --app-token xapp-... --non-interactive
```

Each project MUST use a unique prefix. Two projects with the same prefix will
share channels and interfere with each other.

### Required Slack bot scopes

The setup script configures these automatically via the manifest. If setting up
manually, the bot needs these OAuth scopes:

- chat:write (send messages)
- channels:read (list public channels)
- channels:history (read public channel history for polling)
- channels:manage (create public channels, fallback)
- channels:join (join public channels)
- groups:read (list private channels)
- groups:history (read private channel history for polling)
- groups:write (create private channels)
- groups:write.invites (invite members to private channels)
- users:read (look up user IDs for --invite-user)
- users:read.email (look up users by email for --invite-user)

## 4. Configure the project

Create .claude/orchestrator-config.yaml if your project uses non-default commands:

```yaml
build_command: "pnpm run build"
test_command: "pnpm test"
dev_server_command: "pnpm dev"
dev_server_port: 3000
```

Skip this step if the defaults work for your project.

## 5. Create backlog directories

```bash
mkdir -p docs/defect-backlog docs/feature-backlog docs/completed-backlog/defects docs/completed-backlog/features
```

## 6. Update .gitignore

The orchestrator creates several transient files that must not be committed.
Add these to your project's .gitignore:

```gitignore
# Plan orchestrator - transient/generated files
.claude/plans/task-status.json
.claude/plans/current-plan.yaml
.claude/plans/.stop
.claude/plans/logs/
.claude/subagent-status/
.claude/agent-claims.json

# Slack config contains tokens - never commit
.claude/slack.local.yaml
.claude/slack-*.json
```

If you skip this step, you risk committing bot tokens or polluting your repo
with transient status files that change on every pipeline run.

## 7. Start the pipeline

```bash
python scripts/auto-pipeline.py
```

The pipeline watches docs/defect-backlog/ and docs/feature-backlog/ for new
markdown files. When it finds one, it creates a design + plan and executes it.

To process one item and exit:
```bash
python scripts/auto-pipeline.py --once
```

To test without making changes:
```bash
python scripts/auto-pipeline.py --dry-run
```

## 8. Submit work via Slack

Send messages to your Slack channels:

- Post to #myproject-features: describe a feature you want
- Post to #myproject-defects: describe a bug to fix
- Post to #myproject-questions: ask about pipeline status
- Post to #myproject-notifications: "stop" to halt the pipeline

Or create markdown files directly in the backlog directories:

```bash
cat > docs/feature-backlog/01-my-first-feature.md << 'EOF'
# My First Feature

## Status: Open

## Priority: Medium

## Summary
Description of what the feature should do.

## Acceptance Criteria
- Criterion 1
- Criterion 2
EOF
```

## Verification

To confirm everything is working:

1. Check Slack config: python -c "import yaml; print(yaml.safe_load(open('.claude/slack.local.yaml')))"
2. Start pipeline: python scripts/auto-pipeline.py --dry-run --once
3. Post a test message to your notifications channel

## File reference

| File | Purpose |
|------|---------|
| .claude/slack.local.yaml | Slack tokens and config (gitignored, never commit) |
| .claude/slack.local.yaml.template | Template with manual setup instructions |
| .claude/orchestrator-config.yaml | Project build/test commands |
| scripts/setup-slack.py | Interactive Slack setup |
| scripts/auto-pipeline.py | Pipeline daemon |
| scripts/plan-orchestrator.py | Plan execution engine |
| docs/defect-backlog/ | Drop defect .md files here |
| docs/feature-backlog/ | Drop feature .md files here |
| docs/completed-backlog/ | Archived completed items |

## Upgrading

### From plugin install

```bash
claude plugin update plan-orchestrator
```

### From manual copy (scripts copied into your project)

If you previously copied plan-orchestrator.py and auto-pipeline.py directly
into your project:

1. Back up any local modifications you made to the scripts
2. Replace the scripts with the latest versions:

```bash
cp /path/to/claude-plan-orchestrator/scripts/plan-orchestrator.py scripts/
cp /path/to/claude-plan-orchestrator/scripts/auto-pipeline.py scripts/
cp /path/to/claude-plan-orchestrator/scripts/setup-slack.py scripts/
```

3. Update agent definitions and skills:

```bash
cp -r /path/to/claude-plan-orchestrator/.claude/agents/ .claude/agents/
cp -r /path/to/claude-plan-orchestrator/.claude/skills/ .claude/skills/
```

4. Check for new .gitignore entries by comparing against the list in step 6
5. If you had Slack set up with the old webhook format (webhook_url instead of
   bot_token), re-run the Slack setup:

```bash
python scripts/setup-slack.py --prefix your-existing-prefix
```

### From webhook-based Slack to app-based Slack

Older versions used a Slack incoming webhook (webhook_url in config). The
current version uses a Slack App with bot_token and app_token. To migrate:

1. Run the setup script to create a new Slack app:

```bash
python scripts/setup-slack.py --prefix your-prefix
```

2. The script writes a new .claude/slack.local.yaml replacing the old one
3. Delete the old webhook from your Slack workspace (Settings > Incoming Webhooks)
