# Slack Inbound Message Polling

## Status: Open

## Priority: Medium

## Summary

Poll the Slack channel for new human messages at natural control-flow boundaries
in the auto-pipeline and orchestrator. When the human posts a message, classify
it and take appropriate action: create a backlog item (feature or defect), answer
a pending question, adjust execution (pause/skip/stop), or acknowledge an
informational message.

This closes the loop on the Slack communication channel by letting the human
send work to the pipeline via Slack instead of creating markdown files manually.

## Integration Points

Poll for new messages at the same places the pipeline already checks for new work:

**Auto-pipeline (main_loop):**
- Before scanning backlogs (line ~1597: scan_all_backlogs)
- After completing each work item (line ~1648: after process_item returns)
- During idle wait (line ~1615: when waiting for filesystem events)

**Orchestrator (main execution loop):**
- Between tasks (after task completion, before starting next task)
- After validation results (human may want to override retry/skip)

These are the moments when control returns to the loop and the system is
ready to accept new input. No background threads needed - just a function
call at each checkpoint.

## Proposed Design

### Channel-Based Routing

Use a naming convention to auto-discover channels and route messages by
purpose, mirroring how the file-based backlog uses directory names:

| Channel Name | Purpose | Inbound Action | Outbound |
|-------------|---------|----------------|----------|
| #orchestrator-features | Feature requests | Create feature backlog item | Feature ideas from agents |
| #orchestrator-defects | Defect reports | Create defect backlog item | Defect reports from agents |
| #orchestrator-questions | Q&A with human | Answer questions / receive answers | Agent questions |
| #orchestrator-notifications | Status updates | Control commands (stop/pause/status) | All status updates |

On startup (and periodically), call conversations.list and filter to
channels matching the prefix "orchestrator-" where is_member=true.
The channel name determines how messages are classified - no prefix
parsing needed in the message text itself.

    CHANNEL_ROLES = {
        "orchestrator-features": "feature",
        "orchestrator-defects": "defect",
        "orchestrator-questions": "question",
        "orchestrator-notifications": "control",
    }

The human creates whichever channels they want. If only
#orchestrator-notifications exists, the bot sends everything there and
uses message-prefix classification as a fallback for inbound. If all four
exist, routing is automatic based on which channel the message lands in.

Config stays simple - just the bot credentials, no channel IDs needed:

    slack:
      enabled: true
      bot_token: "xoxb-..."
      app_token: "xapp-..."
      channel_prefix: "orchestrator"     # default, can be customized

The bot discovers channels by prefix on each poll cycle. If no matching
channels are found, falls back to the legacy single channel_id if present.

**Outbound routing:** Agent status updates go to #orchestrator-notifications.
Agent-reported defects go to #orchestrator-defects. Ideas go to
#orchestrator-features. Questions go to #orchestrator-questions. If a
target channel doesn't exist, falls back to #orchestrator-notifications,
then to the legacy channel_id.

### Message Tracking

Track the last-read message timestamp per channel to avoid re-processing:

    SLACK_LAST_READ_PATH = ".claude/slack-last-read.json"

Store {"channels": {"C0AFR...": "1234567890.123", "C0BXY...": "1234567891.456"}}
after each poll. On startup, read this file to resume from where we left off.
If missing, only process messages from this session forward (use current timestamp).

### Poll Function

    def poll_slack_messages(self) -> list[SlackMessage]:
        """Fetch unread messages from all monitored channels since last poll.
        Returns empty list if disabled, no new messages, or on error."""

For each monitored channel, calls conversations.history with oldest=last_ts.
Filters out bot messages (our own posts). Returns a flat list of human
messages tagged with their source channel.

### Message Classification

Classification is primarily channel-based. The channel the message arrives
in determines the action:

| Source Channel | Action |
|---------------|--------|
| #orchestrator-features | Create feature backlog item (title = first line, body = rest) |
| #orchestrator-defects | Create defect backlog item (title = first line, body = rest) |
| #orchestrator-questions | Answer using project context via haiku LLM call |
| #orchestrator-notifications | Parse as control command (see below) |

Control commands in #orchestrator-notifications use simple prefix matching:

| Pattern | Action |
|---------|--------|
| "stop" or "pause" | Write stop semaphore, confirm in channel |
| "skip" | Skip current task, confirm in channel |
| "status" or "status?" | Post current pipeline status |
| reply to a bot question | Write answer for pending send_question |
| anything else | Log and acknowledge |

**Fallback (single channel mode):** If only one channel exists (e.g.,
the legacy channel_id), all messages arrive there and prefix-based
classification is used: "feature:", "defect:", "?", "stop", "status",
etc. This preserves backward compatibility with the single-channel setup.

### Answering Human Questions

When a message is classified as a question (contains "?" or starts with
"what", "how", "where", "when", "why", "which", "can", "is", "are"):

Use a lightweight LLM call (haiku) with project context to answer. The
context provided to the LLM includes:
- Current pipeline state (idle/processing, current item, queue depth)
- Recent task results (last 5 completed/failed tasks)
- Backlog summary (count of open features, defects, on-hold items)
- Plan status (which plans are in progress, completed, pending)

Example interactions:
- "what's in the backlog?" -> Lists open features and defects with priorities
- "how much budget is left?" -> Reports session cost and remaining quota
- "which plan is running?" -> Shows current plan name and progress
- "why did task 3.1 fail?" -> Reads the task result message from the YAML

The LLM call is bounded: max 500 input tokens of context, haiku model,
single-turn. This keeps cost per question under $0.001.

If the question cannot be answered from available context, reply with
"I don't have enough context to answer that. Try asking in the terminal
session where you have full Claude access."

### Backlog Item Creation

When a message is classified as new_feature or new_defect:

1. Extract the title from the first line (after the prefix)
2. Extract the description from subsequent lines (if any)
3. Generate the next available number (scan existing backlog files)
4. Create the markdown file in docs/feature-backlog/ or docs/defect-backlog/
5. Confirm in Slack: "Created feature backlog item: 16-cache-ttl-support.md"

The markdown file follows the standard backlog format:

    # {Title}

    ## Status: Open

    ## Priority: Medium

    ## Summary

    {Description from Slack message}

    ## Source

    Created from Slack message by {user} at {timestamp}.

### Pipeline Status Response

When the human asks "status":

    *Pipeline Status*
    State: processing | idle | paused
    Current item: {slug} (if processing)
    Session: {items_completed} completed, {items_failed} failed
    Budget: {used}% of {ceiling}
    Uptime: {duration}

### SlackNotifier Extensions

Add to the existing SlackNotifier class:

    def poll_messages(self) -> list[dict]:
        """Fetch unread messages since last poll."""

    def classify_message(self, text: str) -> tuple[str, str, str]:
        """Returns (classification, title, body)."""

    def create_backlog_item(self, item_type: str, title: str, body: str) -> str:
        """Create a backlog .md file. Returns the file path."""

    def process_inbound(self) -> None:
        """Poll, classify, and act on all new messages. Call at checkpoints."""

The main_loop and orchestrator just call slack.process_inbound() at each
checkpoint. All logic is encapsulated in the notifier.

## Verification

- Post "feature: Add cache TTL support" in Slack
- Verify a backlog file is created with correct format
- Post "defect: Broken import in auth module" in Slack
- Verify a defect backlog file is created
- Post "status" in Slack, verify status response appears
- Post "stop" in Slack, verify pipeline stops gracefully
- Verify bot's own messages are ignored (no feedback loops)
- Verify last-read tracking works across pipeline restarts

## Files Likely Affected

| File | Change |
|------|--------|
| scripts/plan-orchestrator.py | SlackNotifier.poll_messages, classify_message, create_backlog_item, process_inbound; call process_inbound between tasks |
| scripts/auto-pipeline.py | Call slack.process_inbound() at scan and idle checkpoints |
| .claude/slack-last-read.json | Message tracking state (gitignored) |
| .gitignore | Add slack-last-read.json pattern (already covered by slack-*.json) |

## Dependencies

- 13-slack-agent-communication.md (completed): SlackNotifier infrastructure
- 14-slack-app-migration.md (completed): Web API transport with channels:history
