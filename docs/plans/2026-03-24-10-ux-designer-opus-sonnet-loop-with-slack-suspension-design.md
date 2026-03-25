# Design: UX Designer Opus/Sonnet Loop with Slack Suspension

**Feature:** 10-ux-designer-opus-sonnet-loop-with-slack-suspension
**Date:** 2026-03-24
**Source:** docs/feature-backlog/10-ux-designer-opus-sonnet-loop-with-slack-suspension.md

## Status

**Part 1 (Opus/Sonnet loop): COMPLETE.**
`ux-designer.md` and `ux-implementer.md` agents are already implemented and production-ready.

**Part 2 (Slack suspension): Infrastructure exists, wiring incomplete.**
The suspension marker system and Slack suspension question posting are built. What's missing is
the connection between task execution and Slack, plus the reinstatement path.

## Overview

When the `ux-designer` (Opus) agent cannot resolve a design question on its own, it writes
`task-status.json` with `status: "suspended"`. The pipeline must then:

1. Create a suspension marker file in `.claude/suspended/<slug>.json`
2. Post the question to the Slack channel for the item type
3. Continue processing other backlog items
4. When the user replies in Slack, update the marker with the answer
5. On the next scan cycle, reinstate the task by resetting it to "pending" and injecting the answer
6. The `ux-designer` agent reads the injected answer on resumption and uses it as a pre-filled Q&A entry

## Architecture

### What's already built

- `langgraph_pipeline/shared/suspension.py` — marker file CRUD: `create_suspension_marker()`,
  `read_suspension_marker()`, `clear_suspension_marker()`, `is_item_suspended()`,
  `get_suspension_answer()`
- `langgraph_pipeline/slack/suspension.py` — `SlackSuspension.post_suspension_question()` and
  `_check_all_suspensions()` (polls Slack threads and writes answers to marker files)
- `langgraph_pipeline/slack/__init__.py` — exposes `post_suspension_question()` and
  `check_suspension_reply()` on `SlackNotifier`
- `langgraph_pipeline/slack/poller.py` — calls `check_suspensions` callback on each poll cycle
- `langgraph_pipeline/executor/nodes/task_runner.py` — detects `status: "suspended"` from
  `task-status.json` and marks the task as `"suspended"` in the plan YAML
- `.claude/agents/ux-designer.md` — writes `task-status.json` with `"suspended"` status

### What needs to be implemented

#### 1. task_runner.py — Create suspension marker on detection

When `task_runner.py` detects `outcome == "suspended"`:

- Read `question` and `question_context` from `status_dict`
- Derive `source_item` from `plan_data["meta"]["source_item"]`
- Derive `slug` from `Path(source_item).stem`
- Derive `item_type` by checking if "defect" or "feature" is in `source_item`
- Call `create_suspension_marker(slug, item_type, source_item, plan_path, task_id, question, question_context)`

This is the only change to the executor layer — the marker file is created here immediately.

#### 2. cli.py — Two new helpers called in the scan loop

**`_post_pending_suspension_questions(slack)`**

Scans `.claude/suspended/*.json` for markers without a `slack_thread_ts`. For each one:
- Calls `slack.post_suspension_question(slug, item_type, question, question_context)`
- Writes the returned `thread_ts` and `channel_id` back to the marker file
- If `slack` is None, skips posting (marker stays for next cycle)

**`_reinstate_answered_suspensions()`**

Scans `.claude/suspended/*.json` for markers where `answer` is a non-empty string. For each one:
- Reads `plan_path` and `task_id` from the marker
- Resets the task status from `"suspended"` to `"pending"` in the plan YAML
- Writes a `human_answer` field and a `human_question` field onto the task dict in the YAML
- Saves the updated YAML
- Deletes the suspension marker file

These two helpers are called at the top of each scan iteration, before `_pre_scan()`.

#### 3. ux-designer.md — Handle human_answer on resumption

On agent startup, after reading the plan and locating the current task, check for `human_answer` field:

- If present, treat it as a pre-resolved Q&A: populate Q&A history with `Q: <human_question> / A: <human_answer>`
- Begin the Sonnet loop with this Q&A history already populated (round 1 of the cap)
- Clear `human_answer` and `human_question` from the task dict is not needed — the YAML is read-only by the agent at this point

## Data Flow

```
ux-designer writes task-status.json (status: "suspended", question, question_context)
    → task_runner.py detects "suspended"
        → task["status"] = "suspended" in YAML
        → create_suspension_marker() writes .claude/suspended/<slug>.json
    → cli.py _post_pending_suspension_questions()
        → slack.post_suspension_question() → Slack channel
        → marker updated with slack_thread_ts, slack_channel_id
    → pipeline continues to next item

[user replies in Slack thread]
    → slack poller _check_all_suspensions()
        → marker["answer"] = reply text

[next scan cycle]
    → cli.py _reinstate_answered_suspensions()
        → task["status"] = "pending", task["human_answer"] = ..., task["human_question"] = ...
        → suspension marker deleted
    → _pre_scan() finds in-progress plan
        → ux-designer agent runs with human_answer in task dict
        → Q&A history pre-populated from human_answer
        → Sonnet loop continues to completion
```

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Create marker in task_runner, post Slack in cli | Keeps executor layer Slack-free; cli.py already has the SlackNotifier |
| Scan SUSPENDED_DIR in cli scan loop | Simple O(n markers) check each cycle; no graph changes needed |
| Inject answer via task dict fields `human_answer`/`human_question` | YAML is the interface between orchestrator and agent; no new files or IPC needed |
| ux-designer reads `human_answer` from task on startup | Agent already reads task data; single place to add resumption logic |
| Skip Slack post if slack is None | Allows --no-slack mode to still benefit from suspension state machine |

## Files to Create or Modify

| File | Change |
|------|--------|
| `langgraph_pipeline/executor/nodes/task_runner.py` | Call `create_suspension_marker()` when outcome == "suspended" |
| `langgraph_pipeline/cli.py` | Add `_post_pending_suspension_questions()`, `_reinstate_answered_suspensions()`, call both in scan loop |
| `.claude/agents/ux-designer.md` | Add resumption logic: check `human_answer` field and pre-populate Q&A history |
| `tests/langgraph/test_suspension_wiring.py` | Unit tests for the two new cli helpers |
