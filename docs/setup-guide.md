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

### Agent Identity (recommended for shared Slack channels)

If multiple projects share Slack channels, add an identity section so each
project's agents sign their messages and filter inbound addressing:

```yaml
identity:
  project: myproject
  agents:
    pipeline: MyProj-Pipeline
    orchestrator: MyProj-Orchestrator
    intake: MyProj-Intake
    qa: MyProj-QA
```

If omitted, display names are derived from the directory name automatically.
Identity enables:
- Outbound messages signed with the agent's display name
- Self-loop prevention (agents skip their own echoes)
- Directed messaging with @AgentName (e.g., @MyProj-Pipeline)
- Broadcast messages (no @) are processed by all listeners

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

## Cross-Project Reporting

These steps let your project post defect reports and feature requests to an upstream
orchestrator running in a different codebase. The upstream treats inbound messages
from your bot exactly like messages from a human --- running 5 Whys intake analysis
and adding structured items to its backlog.

### Prerequisites

- Your Slack bot is already set up (step 3 above)
- You have the upstream team's channel prefix (ask them)
- You share a Slack workspace with the upstream project

### Step 1: Identify the upstream channels

Upstream orchestrators create four channels named after their prefix:

| Channel | Purpose |
|---------|---------|
| {prefix}-notifications | Status updates and release announcements |
| {prefix}-defects | Defect reports --- post here to file a bug |
| {prefix}-features | Feature requests --- post here to request a capability |
| {prefix}-questions | Questions answered by the upstream LLM with full pipeline context |

Ask the upstream team for their prefix (e.g., orchestrator-) and verify that
those channels exist in your shared Slack workspace.

### Step 2: Invite your bot to the upstream channels

In each upstream channel you want to post to, open that channel in Slack and run:

```
/invite @YourBotName
```

Repeat for {prefix}-defects and {prefix}-features at minimum. Your bot needs:

- chat:write (post messages to the channel)
- channels:history or groups:history (read history for polling, if monitoring
  upstream notifications)

To verify the invitation worked, run:

```bash
python3 -c "
import yaml, urllib.request, json
cfg = yaml.safe_load(open('.claude/slack.local.yaml'))['slack']
token = cfg['bot_token']
req = urllib.request.Request(
    'https://slack.com/api/users.conversations?types=public_channel,private_channel',
    headers={'Authorization': f'Bearer {token}'}
)
with urllib.request.urlopen(req) as r:
    data = json.loads(r.read())
    for ch in data.get('channels', []):
        print(ch['name'])
"
```

The upstream's channels (e.g., orchestrator-defects) should appear in the output.

### Step 3: Configure the upstream channel prefix

In your .claude/slack.local.yaml, set channel_prefix to the upstream project's prefix:

```yaml
slack:
  enabled: true
  bot_token: xoxb-your-bot-token
  app_token: xapp-your-app-token
  channel_prefix: "orchestrator-"
```

This tells the orchestrator to discover and monitor channels named orchestrator-*.
Because your bot was invited in step 2, those channels appear in the discovery
results and are polled for inbound messages (release notifications, replies, etc.).
Outbound send_defect and send_idea calls also route to these channels.

### Step 4: Configure agent identity

Add an identity section to your .claude/orchestrator-config.yaml so the upstream
orchestrator can identify your messages:

```yaml
identity:
  project: myproject
  agents:
    pipeline: MyProj-Pipeline
    orchestrator: MyProj-Orchestrator
    intake: MyProj-Intake
    qa: MyProj-QA
```

Without explicit identity, display names are derived from your directory name
(e.g., Myproject-Pipeline). Either way, the upstream's self-loop filter skips
messages signed by its own agents, so your messages will always be processed.

### How the agent identity protocol prevents self-loops

When two orchestrators share channels, the identity protocol ensures neither
processes its own echoes:

1. Every outbound message is signed: message text --- *AgentName*
2. On inbound, messages signed by one of our own agents are skipped
3. Messages with @OtherAgent but not @OurAgent are skipped (not addressed to us)
4. Messages with @OurAgent or no @ addressing are processed

This means when your consumer orchestrator posts to orchestrator-defects, the
upstream processes it (not signed by its own agents). Your own orchestrator ignores
the echo because it recognizes its own signature.

Use @AgentName in the message body to address a specific upstream agent directly
(e.g., @CPO-Pipeline what is the status of feature 17?).

### Quick-start example

Scenario: Your project (prefix cheapoville-) found a bug in the upstream
claude-plan-orchestrator (prefix orchestrator-).

1. Ask the CPO team to run /invite @Cheapoville-Bot in #orchestrator-defects
   and #orchestrator-features.

2. In your .claude/slack.local.yaml:

```yaml
slack:
  enabled: true
  bot_token: xoxb-cheapoville-token
  channel_prefix: "orchestrator-"
```

3. In your .claude/orchestrator-config.yaml:

```yaml
identity:
  project: cheapoville
  agents:
    pipeline: CHV-Pipeline
    orchestrator: CHV-Orchestrator
    intake: CHV-Intake
    qa: CHV-QA
```

4. Post to #orchestrator-defects (or let your pipeline post via send_defect):

```
The plan archiving step fails when a backlog file is moved mid-pipeline.
Steps to reproduce: ...
--- *CHV-Pipeline*
```

The CPO orchestrator's inbound polling picks up the message within 15 seconds,
runs 5 Whys intake analysis, and adds a structured defect item to its backlog.
No manual coordination is required beyond the initial bot invitation.

### Notes

- Your own project channels (e.g., cheapoville-defects) are unaffected. To run
  your own orchestrator for your own work simultaneously, keep a separate
  slack.local.yaml instance pointing to your own prefix. Only one orchestrator
  process should run against a given prefix at a time.
- The upstream's questions channel ({prefix}-questions) is answered by the
  upstream LLM with full pipeline context. Use it to check upstream status or
  ask about a bug before filing a duplicate defect.
- To send a directed question to a specific upstream agent, include @AgentName
  in your message body (e.g., @CPO-Orchestrator is there already a fix in progress
  for the archiving issue?).

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
5. If you have completed items under docs/defect-backlog/completed/ or
   docs/feature-backlog/completed/, move them to the centralized location:

```bash
git mv docs/defect-backlog/completed/* docs/completed-backlog/defects/
git mv docs/feature-backlog/completed/* docs/completed-backlog/features/
rmdir docs/defect-backlog/completed docs/feature-backlog/completed
```

6. If you had Slack set up with the old webhook format (webhook_url instead of
   bot_token), re-run the Slack setup:

```bash
python scripts/setup-slack.py --prefix your-existing-prefix
```

### To v1.7.0 (agent identity protocol)

v1.7.0 adds the agent identity protocol for shared Slack channels. No action
is required --- the system works without configuration. But if multiple projects
share Slack channels, you should add identity configuration:

1. Add an identity section to .claude/orchestrator-config.yaml:

```yaml
identity:
  project: myproject
  agents:
    pipeline: MyProj-Pipeline
    orchestrator: MyProj-Orchestrator
    intake: MyProj-Intake
    qa: MyProj-QA
```

2. Choose short, distinctive names. They appear at the end of every Slack
   message (e.g., "Task completed --- *MyProj-Orchestrator*").

3. Use @AgentName in Slack messages to direct them to a specific agent.
   Messages without @addressing are broadcast to all listeners.

If you skip this step, agent names default to {DirName}-Pipeline,
{DirName}-Orchestrator, etc., derived from the current directory name.

### From webhook-based Slack to app-based Slack

Older versions used a Slack incoming webhook (webhook_url in config). The
current version uses a Slack App with bot_token and app_token. To migrate:

1. Run the setup script to create a new Slack app:

```bash
python scripts/setup-slack.py --prefix your-prefix
```

2. The script writes a new .claude/slack.local.yaml replacing the old one
3. Delete the old webhook from your Slack workspace (Settings > Incoming Webhooks)
