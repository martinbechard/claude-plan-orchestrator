# Slack Inbound Message Polling Design

> **For Claude:** REQUIRED SUB-SKILL: Use the implement skill to execute this plan task-by-task.

**Goal:** Poll the Slack channel for new human messages at control-flow boundaries
in the auto-pipeline and orchestrator. Classify each message and take action:
create backlog items, answer questions, respond to control commands (stop/skip/status),
or acknowledge informational messages.

**Architecture:** Extends the existing SlackNotifier class with inbound message
handling. Uses the conversations.history Web API (same stdlib urllib.request
transport as _post_message) to fetch new messages. A simple last-read timestamp
tracker avoids re-processing. Message classification uses prefix matching with
an extensible pattern table. All processing is synchronous at existing checkpoints
- no background threads needed for polling.

**Tech Stack:** Python stdlib (urllib.request, json, os), existing SlackNotifier

---

## Key Design Decisions

1. **Synchronous polling at checkpoints.** The auto-pipeline and orchestrator
   already have natural control-flow boundaries where they check for new work or
   stop signals. We poll for Slack messages at these same points. This avoids
   background threads and keeps the single-threaded model simple.

2. **conversations.history with oldest parameter.** The Slack Web API provides
   conversations.history which returns messages in a channel after a given
   timestamp. Combined with a persisted last-read timestamp, this gives us
   exactly-once processing with no message loss across restarts.

3. **Prefix-based classification.** The initial classifier uses simple string
   prefix matching (e.g., "feature:", "defect:", "stop", "status"). This is
   fast, deterministic, and free (no LLM calls). A future enhancement could
   add haiku-based classification for ambiguous messages.

4. **Question answering with LLM.** When a message ends with "?" or starts
   with question words, use a haiku call with pipeline context to answer.
   Bounded to 500 input tokens to keep cost under $0.001 per question.

5. **Bot message filtering.** Messages from bots (including our own) are
   filtered out by checking the "bot_id" or "subtype" fields in the Slack
   API response. This prevents feedback loops.

6. **Last-read state in .claude/slack-last-read.json.** Already covered by
   the existing .gitignore pattern (.claude/slack-*.json). On first run,
   uses current timestamp to avoid processing historical messages.

7. **channels:history scope required.** The config template must be updated
   to include this scope in the setup instructions. This is the only new
   Slack permission needed.

---

## New Constants

    SLACK_LAST_READ_PATH = ".claude/slack-last-read.json"
    SLACK_INBOUND_POLL_LIMIT = 20  # max messages per poll

---

## Message Classification Table

| Pattern | Classification | Action |
|---------|---------------|--------|
| starts with "feature:" or "enhancement:" | new_feature | Create feature backlog item |
| starts with "defect:" or "bug:" | new_defect | Create defect backlog item |
| starts with "stop" or "pause" | control_stop | Write stop semaphore |
| starts with "skip" | control_skip | Skip current task |
| starts with "status" or "status?" | info_request | Post pipeline status |
| ends with "?" or starts with question word | question | Answer via LLM |
| reply to a question message | question_answer | Write answer file |
| anything else | acknowledgement | Log and confirm receipt |

---

## New SlackNotifier Methods

### poll_messages() -> list[dict]

Fetch unread messages since last poll using conversations.history API.
Filter out bot messages. Update last-read timestamp. Return list of
human message dicts with text, user, ts fields.

### classify_message(text: str) -> tuple[str, str, str]

Classify a message by its text content. Returns (classification, title, body).
Uses case-insensitive prefix matching against the classification table.

### create_backlog_item(item_type: str, title: str, body: str, user: str, ts: str) -> str

Create a backlog markdown file (feature or defect). Scans existing backlog
files to determine the next available number. Returns the created file path.
Confirms creation in Slack.

### handle_control_command(command: str) -> None

Handle stop/skip/status commands. For "stop"/"pause", writes the stop
semaphore file. For "skip", writes a skip marker. For "status", posts
current pipeline state.

### answer_question(question: str) -> None

Use a lightweight LLM call (haiku) with pipeline context to answer.
Posts the answer back to Slack. If unable to answer, says so.

### process_inbound() -> None

Main entry point called at checkpoints. Polls for messages, classifies
each one, and dispatches to the appropriate handler. Catches all exceptions
to never disrupt the pipeline.

---

## Integration Points

### Auto-pipeline (main_loop)

Call slack.process_inbound() at three points:
1. Before scan_all_backlogs() (line ~1597)
2. After each process_item() returns (line ~1648)
3. During idle wait before new_item_event.wait() (line ~1615)

### Orchestrator (main execution loop)

Call slack.process_inbound() at two points:
1. At the top of the while True loop, after stop/circuit-breaker checks
2. After validation results (before retry decision)

---

## Files to Modify

| File | Change |
|------|--------|
| scripts/plan-orchestrator.py | Add SLACK_LAST_READ_PATH and SLACK_INBOUND_POLL_LIMIT constants. Add poll_messages, classify_message, create_backlog_item, handle_control_command, answer_question, process_inbound methods to SlackNotifier. |
| scripts/auto-pipeline.py | Call slack.process_inbound() at scan, post-item, and idle checkpoints in main_loop. |
| .claude/slack.local.yaml.template | Add channels:history to the Bot Token Scopes comment. |
| tests/test_slack_notifier.py | Add tests for poll_messages, classify_message, create_backlog_item, process_inbound. |

---

## Phase 1: Config Template Update

### Task 1.1: Add channels:history scope to config template

Update .claude/slack.local.yaml.template to list channels:history in the
Bot Token Scopes comment (step 3).

---

## Phase 2: Message Tracking and Polling

### Task 2.1: Add poll_messages and last-read tracking

Add SLACK_LAST_READ_PATH and SLACK_INBOUND_POLL_LIMIT constants.
Add _load_last_read, _save_last_read, and poll_messages methods.
poll_messages calls conversations.history, filters bots, updates timestamp.

### Task 2.2: Add classify_message

Add classify_message method with prefix-based pattern matching table.
Returns (classification, title, body) tuple.

### Task 2.3: Add create_backlog_item

Add create_backlog_item method that scans existing backlog files for
next available number, creates the markdown file, and confirms in Slack.

### Task 2.4: Add handle_control_command and answer_question

Add handle_control_command for stop/skip/status.
Add answer_question stub (posts "question received" for now; LLM
integration is a future enhancement).

### Task 2.5: Add process_inbound orchestration method

Add process_inbound() that calls poll_messages, classifies each,
and dispatches to handlers. Wraps everything in try/except.

---

## Phase 3: Integration

### Task 3.1: Integrate process_inbound into auto-pipeline

Add slack.process_inbound() calls at scan, post-item, and idle
checkpoints in auto-pipeline.py main_loop.

### Task 3.2: Integrate process_inbound into orchestrator

Add slack.process_inbound() calls between tasks and after validation
in plan-orchestrator.py main execution loop.

---

## Phase 4: Unit Tests

### Task 4.1: Test poll_messages and last-read tracking

Test poll_messages with mocked API responses. Test bot filtering.
Test last-read persistence. Test first-run behavior (no prior state).

### Task 4.2: Test classify_message

Test all classification patterns. Test case insensitivity.
Test multi-line messages. Test edge cases (empty string, whitespace).

### Task 4.3: Test create_backlog_item

Test file creation with correct format. Test number sequencing.
Test both feature and defect types. Use tmp_path for isolation.

### Task 4.4: Test process_inbound end-to-end

Test full flow: poll -> classify -> dispatch. Test error resilience.
Test disabled notifier is a no-op.

---

## Phase 5: Verification

### Task 5.1: Syntax and test verification

Verify both scripts compile. Run all tests. Verify dry-run works.
