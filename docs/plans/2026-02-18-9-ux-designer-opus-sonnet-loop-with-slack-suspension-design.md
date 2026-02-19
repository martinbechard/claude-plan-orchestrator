# UX Designer Opus/Sonnet Loop with Slack-Based Question Suspension

## Architecture Overview

This feature introduces a two-part enhancement to the UX design pipeline:

**Part 1 - Opus/Sonnet Design Loop:** The ux-designer agent becomes a stateful
Opus orchestrator that produces a design brief, invokes a Sonnet subagent
(ux-implementer) to realize the design, and loops when Sonnet returns questions
instead of a complete design. Each Sonnet invocation is fully stateless -- Opus
re-injects the full Q&A history on every call. The loop is capped at 3 rounds
to prevent runaway costs.

**Part 2 - Slack-Based Question Suspension:** When Opus cannot resolve a design
question on its own, the work item is suspended. The pipeline posts the question
to the appropriate Slack channel and continues processing other items. When the
user replies (via Slack thread), the suspended item is reinstated with the answer
injected as context.

```
Part 1 Flow:
  plan-orchestrator
      |
      v
  ux-designer (Opus) -- produces design brief
      |
      +---> run_claude_task(ux-implementer prompt, model=sonnet)
      |         |
      |         +---> STATUS: COMPLETE + design doc
      |         |         (Opus writes output, done)
      |         |
      |         +---> STATUS: QUESTION + structured question
      |                   (Opus answers, re-injects Q&A, loops)
      |
      +---> (max 3 rounds) best-effort design with open questions logged

Part 2 Flow:
  ux-designer (Opus) -- cannot answer question
      |
      v
  Writes suspension marker file: .claude/suspended/<slug>.json
  Posts question to Slack channel (features/defects)
  Returns status: "suspended" in task-status.json
      |
      v
  plan-orchestrator marks task as "suspended"
  auto-pipeline skips suspended items
      |
      v
  Slack background poller detects threaded reply
  Writes answer to suspension marker file
  Clears suspension state
      |
      v
  auto-pipeline picks up item on next cycle
  Opus receives answer as injected context
```

## Key Files to Create

| File | Purpose |
|------|---------|
| .claude/agents/ux-implementer.md | Sonnet-based design implementer agent |

## Key Files to Modify

| File | Change |
|------|--------|
| .claude/agents/ux-designer.md | Rewrite as Opus orchestrator with loop logic |
| scripts/plan-orchestrator.py | Add suspension handling, new task status, Slack question routing |
| scripts/auto-pipeline.py | Add suspended item state, skip logic, reinstatement |

## Design Decisions

### 1. Sonnet Output Protocol

Sonnet must return output with a rigid status prefix to avoid parsing ambiguity:

```
STATUS: COMPLETE
---
<full design document content>
```

or

```
STATUS: QUESTION
QUESTION: <structured question text>
CONTEXT: <what information is needed and why>
```

Opus parses the first line to determine the response type. This avoids
reliance on natural language parsing which would be fragile.

### 2. Loop Cap

The loop is capped at 3 rounds (configurable via UX_DESIGN_MAX_ROUNDS constant).
After the cap, Opus documents remaining open questions in a dedicated section of
the design output rather than silently guessing. This preserves transparency
without blocking progress.

### 3. Stateless Sonnet Re-injection

Each Sonnet invocation receives the full accumulated Q&A history prepended
to the design brief. Since Sonnet has no memory between calls, the entire
context must be re-sent every time. The format is a numbered Q&A list:

```
## Prior Design Q&A
Q1: <question from round 1>
A1: <Opus answer from round 1>
Q2: <question from round 2>
A2: <Opus answer from round 2>
```

### 4. Suspension State Machine

Suspended items use a marker file at .claude/suspended/<slug>.json containing:

```json
{
  "slug": "9-ux-designer-feature",
  "item_type": "feature",
  "item_path": "docs/feature-backlog/9-ux-designer-feature.md",
  "plan_path": ".claude/plans/9-ux-designer-feature.yaml",
  "task_id": "0.2",
  "question": "Should the dashboard use a grid or list layout?",
  "question_context": "The spec mentions both options...",
  "slack_thread_ts": "1708300000.000100",
  "slack_channel_id": "C12345",
  "suspended_at": "2026-02-18T10:00:00Z",
  "timeout_minutes": 1440
}
```

The auto-pipeline scan_directory() function checks for a matching suspension
marker and skips the item. The Slack background poller watches for threaded
replies on the question message and writes the answer back into the marker file.
On the next pipeline cycle, the item is reinstated with the answer injected.

### 5. Slack Thread Correlation

Questions are posted as messages in the type-specific Slack channel (features
or defects). The message includes the item slug for identification. The Slack
thread_ts of the question message is stored in the suspension marker. The
background poller checks for replies in the thread. This uses Slack's native
threading to scope replies to the correct question -- no manual ID scheme needed.

### 6. Task Status: "suspended"

A new task status value "suspended" is added alongside pending/in_progress/
completed/failed/skipped. When plan-orchestrator encounters a "suspended" status
in the task-status.json written by the ux-designer agent, it preserves the task
in its current state and exits cleanly. The auto-pipeline treats the entire
work item as suspended until the question is answered.

### 7. Implementation Phasing

Part 1 (Opus/Sonnet loop) and Part 2 (Slack suspension) are implemented in
separate phases with independent tests. Part 1 is self-contained within the
agent definitions and plan-orchestrator's task execution. Part 2 requires
changes to the auto-pipeline state machine and Slack message handling.

## Constants

```python
# ux-designer loop configuration
UX_DESIGN_MAX_ROUNDS = 3
UX_IMPLEMENTER_MODEL = "sonnet"
UX_ORCHESTRATOR_MODEL = "opus"

# Suspension configuration
SUSPENDED_DIR = ".claude/suspended"
SUSPENSION_TIMEOUT_MINUTES = 1440  # 24 hours default
```
