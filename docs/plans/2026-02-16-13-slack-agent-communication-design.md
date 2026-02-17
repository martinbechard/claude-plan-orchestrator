# Slack Communication Channel for Agents - Design Document

**Goal:** Allow orchestrator agents to communicate with the human operator via Slack. Agents send status updates, ask blocking questions, report defects, and propose feature ideas as Slack messages. The human can respond to questions directly in Slack, unblocking agents without needing to be at the terminal. The feature is strictly opt-in: dormant unless a local Slack configuration file exists.

**Architecture:** A SlackNotifier class in plan-orchestrator.py reads configuration from .claude/slack.local.yaml (gitignored). It integrates at the same lifecycle points where send_notification() is already called, plus additional hooks for validation failures and budget thresholds. For receiving answers to questions, the initial implementation uses file-based polling (Approach B from the backlog spec) - the simplest approach requiring no external infrastructure. The auto-pipeline.py gains a thin wrapper that delegates to the same SlackNotifier. Agent-initiated messages use the existing task-status.json with an optional slack_messages field.

**Tech Stack:** Python 3 (urllib.request for HTTP POST to Slack webhooks, no new dependencies), YAML (slack.local.yaml configuration), JSON (Slack Block Kit payloads, slack-pending-question.json / slack-answer.json for polling)

---

## Architecture Overview

### Configuration

Configuration lives in .claude/slack.local.yaml - a gitignored file alongside other .claude/ local files. This is consistent with the project YAML-based configuration pattern.

    # .claude/slack.local.yaml
    slack:
      enabled: true
      webhook_url: "https://hooks.slack.com/services/T.../B.../xxx"
      channel: "#orchestrator-updates"       # display only
      notify:
        on_plan_start: true
        on_task_complete: true
        on_plan_complete: true
        on_validation_fail: true
        on_budget_threshold: true
        on_question: true
        on_defect_found: true
        on_idea_found: true
      questions:
        enabled: true
        timeout_minutes: 60
        fallback: "skip"                     # skip | fail | retry

### Dependencies

- Feature 06 (Token Usage Tracking): Cost data included in status messages (already implemented)
- Feature 07 (Quota-Aware Execution): Budget threshold triggers Slack notifications (already implemented)
- Feature 03 (Per-Task Validation Pipeline): Validation failure triggers Slack questions (already implemented)

### SlackNotifier Class

A standalone class in plan-orchestrator.py (below the existing send_notification function):

    class SlackNotifier:
        """Sends messages to Slack via Incoming Webhooks.

        Reads .claude/slack.local.yaml on init. If the file is missing or
        slack.enabled is false, all methods are no-ops (silent, no errors).
        Uses urllib.request (stdlib only) for HTTP POST to the webhook URL.
        """

        def __init__(self, config_path: str = SLACK_CONFIG_PATH)
        def is_enabled(self) -> bool
        def send_status(self, message: str, level: str = "info") -> None
        def send_question(self, question: str, options: list[str],
                          timeout_minutes: int = 0) -> str | None
        def send_defect(self, title: str, description: str,
                        file_path: str = "") -> None
        def send_idea(self, title: str, description: str) -> None
        def _post_webhook(self, payload: dict) -> bool

Level-to-emoji mapping for send_status:
- "info": blue_circle
- "success": white_check_mark
- "error": x
- "warning": warning

### Question Flow (File-Based Polling)

For blocking questions (send_question), the flow is:

1. SlackNotifier posts the question to Slack with option buttons listed as text
2. Writes .claude/slack-pending-question.json with question metadata + timestamp
3. Polls for .claude/slack-answer.json at a configurable interval (default 30s)
4. If answer file appears (written by human or external watcher), reads and returns it
5. If timeout_minutes elapses, applies the configured fallback (skip/fail/retry)
6. Cleans up both files after resolution

The human answers by creating .claude/slack-answer.json manually or via a lightweight companion script. This avoids requiring ngrok, cloud functions, or Slack Bolt for the initial implementation.

    # .claude/slack-pending-question.json (written by SlackNotifier)
    {
      "question": "Validation found 2 FAIL findings. Retry or skip?",
      "options": ["retry", "skip", "details"],
      "asked_at": "2026-02-16T15:30:00Z",
      "timeout_minutes": 60
    }

    # .claude/slack-answer.json (written by human/watcher)
    {
      "answer": "retry"
    }

### Orchestrator Integration Points

The SlackNotifier hooks into existing lifecycle events:

| Event | Where in Code | Method |
|-------|--------------|--------|
| Plan starts | run_plan() entry (~line 2585) | send_status("Plan X started: N tasks") |
| Task completes | after task SUCCESS (~line 2970+) | send_status("Task X.Y completed") |
| Task fails | after max_attempts (~line 2938) | send_status("Task X.Y failed", level="error") |
| Validation fails | after validation FAIL verdict | send_question("Retry or skip?") |
| Plan completes | after "All tasks completed" (~line 2888) | send_status("Plan complete: summary") |
| Budget threshold | BudgetGuard.can_proceed() returns False | send_status("Budget reached", level="warning") |
| Design tie | future: judge scoring | send_question("Pick winner: A or B") |
| Stop requested | check_stop_requested() true | send_status("Graceful stop", level="warning") |

### Agent-Initiated Messages (via task-status.json)

The existing task-status.json schema gains an optional slack_messages field:

    {
      "task_id": "3.1",
      "status": "completed",
      "message": "...",
      "slack_messages": [
        {"type": "defect", "title": "Broken import", "description": "..."},
        {"type": "idea", "title": "Cache TTL", "description": "..."}
      ]
    }

After reading the status file in run_claude_task() (~line 2432), the orchestrator iterates over slack_messages and dispatches each via the appropriate SlackNotifier method (send_defect or send_idea).

### Auto-Pipeline Integration

The auto-pipeline.py gains its own SlackNotifier instance, sending:
- Work item started/completed
- Session budget report
- Pipeline paused/stopped with reason

The SlackNotifier class is imported from plan-orchestrator.py to avoid duplication.

### Message Formatting (Slack Block Kit)

Status messages use simple mrkdwn text blocks with emoji:

    {
      "blocks": [
        {
          "type": "section",
          "text": {
            "type": "mrkdwn",
            "text": ":white_check_mark: *Task 2.1 completed* (attempt 1, $0.42, 45s)"
          }
        }
      ]
    }

Questions include options listed as text (file-based polling means buttons are informational):

    {
      "blocks": [
        {
          "type": "section",
          "text": {
            "type": "mrkdwn",
            "text": ":question: *Validation found 2 FAIL findings*\nOptions: `retry` | `skip` | `details`\n_Reply by creating `.claude/slack-answer.json` with `{\"answer\": \"retry\"}`_"
          }
        }
      ]
    }

---

## Key Files

### New Files

| File | Purpose |
|------|---------|
| .claude/slack.local.yaml.template | Example configuration (committed, not the actual config) |
| tests/test_slack_notifier.py | Unit tests for SlackNotifier class |

### Modified Files

| File | Change |
|------|---------|
| scripts/plan-orchestrator.py | Add SlackNotifier class, SLACK_CONFIG_PATH constant, hook into plan/task lifecycle |
| scripts/auto-pipeline.py | Import and use SlackNotifier for pipeline events |
| .gitignore | Add .claude/slack.local.yaml and .claude/slack-*.json patterns |

---

## Design Decisions

1. **File-based polling for questions (Approach B).** The simplest approach requiring zero external infrastructure. No ngrok, no cloud functions, no Slack Bolt app. The human creates a JSON file to answer. A future enhancement can add Slack Interactive Messages (Approach A) for button-click responses.

2. **urllib.request instead of requests library.** Zero new dependencies. The webhook POST is a simple HTTPS call with a JSON body. urllib.request handles this adequately. If the project later adds requests for other reasons, the implementation can be swapped.

3. **SlackNotifier as a class, not extension of send_notification().** The existing send_notification() is a thin wrapper around Claude CLI for email-style notifications. Slack has different formatting needs (Block Kit), question/answer flow, and configuration. A dedicated class is cleaner than overloading the existing function.

4. **Configuration in .claude/slack.local.yaml, not .env.** Consistent with the project YAML-based configuration pattern. The .claude/ directory already contains local files. A .template version is committed for reference.

5. **All methods are no-ops when disabled.** If the config file is missing or slack.enabled is false, every method silently returns without error. This means callers never need to check is_enabled() before calling - the notifier handles it internally. This keeps integration code minimal.

6. **Agent messages via task-status.json, not a separate outbox file.** The backlog spec recommends the status file approach for simplicity. Messages are sent after the task completes, not during. This acceptable latency avoids polling complexity during task execution.

7. **Gitignore both the config and temporary files.** .claude/slack.local.yaml contains the webhook URL (a secret). .claude/slack-pending-question.json and .claude/slack-answer.json are ephemeral polling artifacts. All are gitignored to prevent accidental commits.
