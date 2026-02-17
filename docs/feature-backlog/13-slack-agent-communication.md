# Slack Communication Channel for Agents

## Status: Open

## Priority: Medium

## Summary

Allow orchestrator agents to communicate with the human operator via Slack. Agents
can send status updates, ask blocking questions, report discovered defects, and
propose new feature ideas - all delivered as Slack messages in a configured channel.
The human can respond to questions directly in Slack, unblocking the agent without
needing to be at the terminal.

This is strictly opt-in: the feature is dormant unless the project has a local
Slack configuration file (gitignored, never committed).

## Problem

Today the only way for agents to communicate with the human is through:
- task-status.json (read after the task finishes)
- Log files (reviewed after the fact)
- Terminal output (requires watching the session live)

This means:
1. If an agent has a question, it either guesses or fails. The human only sees the
   question after the run completes.
2. Status updates are invisible until the plan finishes or the human checks logs.
3. When an agent discovers a new defect or feature idea during implementation, it
   has no way to surface it to the human in real time.
4. Overnight or long-running pipeline executions produce no feedback until they stop.

## Use Cases

### Status Updates (agent -> human, non-blocking)
- "Plan 09 started: 6 tasks across 3 phases"
- "Task 2.1 completed (attempt 1, $0.42, 45s)"
- "Plan 09 completed: 6/6 tasks passed, total cost $2.18"
- "Budget threshold reached (91% of weekly quota), pausing execution"

### Questions (agent -> human, blocking)
- "Task 3.1 validation found 2 FAIL findings. Retry or skip? [Retry] [Skip] [Details]"
- "Design competition has 2 candidates with equal scores. Pick winner: [A] [B] [Show both]"
- "Cannot find functional spec for UserProfile page. Where is it? (reply with path)"

### Defect Reports (agent -> human, non-blocking)
- "While implementing feature X, discovered broken import in auth/middleware.ts:42.
  Created defect: docs/defect-backlog/14-broken-auth-import.md"

### Feature Ideas (agent -> human, non-blocking)
- "During code review of task 5.2, identified opportunity: the cache layer could
  support TTL. Drafted: docs/ideas/cache-ttl-support.md"

## Proposed Design

### Local Configuration

Configuration lives in a gitignored local file. Two options for the file location:

**Option A:** .claude/slack.local.yaml (alongside other .claude/ local files)
**Option B:** .env file with SLACK_ prefixed variables

Recommended: Option A for consistency with the project's YAML-based configuration.

    # .claude/slack.local.yaml
    slack:
      enabled: true
      webhook_url: "https://hooks.slack.com/services/T.../B.../xxx"
      channel: "#orchestrator-updates"       # display only, webhook determines actual channel
      notify:
        on_plan_start: true
        on_task_complete: true
        on_plan_complete: true
        on_validation_fail: true
        on_budget_threshold: true
        on_question: true                    # blocking questions via Slack
        on_defect_found: true
        on_idea_found: true
      questions:
        enabled: true                        # allow agents to ask blocking questions
        timeout_minutes: 60                  # auto-skip question after timeout
        fallback: "skip"                     # what to do on timeout: skip | fail | retry

The file must be added to .gitignore to prevent leaking webhook URLs.

### Slack Integration Layer

A small SlackNotifier class in the orchestrator:

    class SlackNotifier:
        def __init__(self, config_path: str)
        def is_enabled(self) -> bool
        def send_status(self, message: str, level: str) -> None
        def send_question(self, question: str, options: list[str]) -> str | None
        def send_defect(self, title: str, description: str, file_path: str) -> None
        def send_idea(self, title: str, description: str) -> None

For sending: use Slack Incoming Webhooks (HTTP POST, no SDK needed, just requests
or urllib). This requires zero dependencies beyond Python stdlib.

For receiving answers to questions: two approaches:

**Approach A: Slack Interactive Messages (recommended)**
Use Block Kit with buttons/menus. When the human clicks a button, Slack sends a
POST to a callback URL. Requires a publicly reachable endpoint (could be a simple
ngrok tunnel or a lightweight cloud function).

**Approach B: Poll-based**
After sending a question, the agent writes a .claude/slack-pending-question.json
file and polls for a .claude/slack-answer.json file. A separate lightweight process
(or Slack bot) watches the channel for replies and writes the answer file. Simpler
but requires a running watcher.

**Approach C: Slack Bolt App (most capable)**
A small Slack Bolt app running locally that handles both sending and receiving.
More setup but provides the richest interaction (threads, reactions, file uploads).

Recommend starting with Approach A for questions + simple webhook POST for notifications.
If interactive messages are too complex to start, fall back to Approach B.

### Message Formatting

Use Slack Block Kit for rich formatting:

Status updates: Simple text with emoji indicators
- Started: blue circle
- Completed: green checkmark
- Failed: red X
- Warning: yellow triangle

Questions: Block Kit with action buttons for each option, plus a text input
for free-form answers.

Defect/idea reports: Attachment blocks with title, description, and a link
to the file path (relative to repo root).

### Orchestrator Integration Points

Hook into existing orchestrator events:

| Event | Where in Code | Slack Action |
|-------|--------------|--------------|
| Plan starts | run_plan() entry | send_status |
| Task completes | after run_task() | send_status |
| Task fails | after run_task() | send_status with error |
| Validation fails | after validation | send_question (retry/skip?) |
| Plan completes | run_plan() exit | send_status with summary |
| Budget threshold | budget check | send_status |
| Design tie | judge scoring | send_question (pick winner) |

### Agent-Initiated Messages

Agents themselves may want to send messages (e.g., "I found a defect"). Two ways
to enable this:

**Via status file extension:** Add optional slack_messages to task-status.json:

    {
      "task_id": "3.1",
      "status": "completed",
      "message": "...",
      "slack_messages": [
        {"type": "defect", "title": "Broken import", "description": "..."},
        {"type": "idea", "title": "Cache TTL", "description": "..."}
      ]
    }

The orchestrator reads these after task completion and forwards to Slack.

**Via a shared file:** Agent writes to .claude/slack-outbox.json during execution.
The orchestrator periodically checks this file and sends queued messages. More
real-time but adds polling complexity.

Recommend the status file approach for simplicity. Messages are sent after the task
completes, not during (acceptable latency for non-blocking messages).

### Auto-Pipeline Integration

The auto-pipeline daemon also sends notifications:
- Work item started/completed
- Session budget report
- Pipeline paused/stopped with reason

## Verification

- Configure .claude/slack.local.yaml with a test webhook
- Run a plan and verify status messages appear in Slack
- Trigger a validation failure and verify the question appears with buttons
- Answer the question in Slack and verify the orchestrator receives the response
- Run with slack.enabled: false and verify zero Slack traffic
- Verify .claude/slack.local.yaml is gitignored

## Files Likely Affected

| File | Change |
|------|--------|
| scripts/plan-orchestrator.py | SlackNotifier class, hook into plan/task lifecycle |
| scripts/auto-pipeline.py | Send notifications for work item events |
| .claude/slack.local.yaml | Local configuration (gitignored template) |
| .gitignore | Add .claude/slack.local.yaml and .claude/slack-*.json |
| task-status.json schema | Optional slack_messages field |

## Dependencies

- None strictly required, but benefits from:
  - 06-token-usage-tracking.md (completed): Cost data in status messages
  - 07-quota-aware-execution.md (completed): Budget threshold notifications
  - 03-per-task-validation-pipeline.md (completed): Validation failure questions
