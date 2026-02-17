# Design: Fix Slack Bot Truncated/Unhelpful Responses on Defect Submission

## Problem

When defects are submitted via Slack, the bot provides truncated, incomplete
responses that lack:
1. Message length enforcement (Slack Block Kit sections have a 3000-char limit)
2. Backlog item ID and filename reference in the confirmation message
3. Clear classification feedback explaining why the submission was classified
   as a defect vs feature

The confirmation flow is also fragmented: create_backlog_item() sends its own
notification, and _run_intake_analysis() sends a separate one, creating
duplicate or confusing messages.

## Architecture Overview

All changes are in scripts/plan-orchestrator.py within the SlackNotifier class.

### Key Files

- scripts/plan-orchestrator.py - All Slack notification and intake logic
- tests/test_plan_orchestrator.py - Unit tests (may need creation)

### Constants to Add

- SLACK_BLOCK_TEXT_MAX_LENGTH = 2900 (safe margin below Slack's 3000-char limit)

### Changes

#### 1. Add _truncate_for_slack() helper method

A private method on SlackNotifier that ensures a message string fits within
Slack Block Kit section text limits. If the message exceeds the limit, it
truncates with an ellipsis indicator showing how many characters were omitted.

Location: After _build_status_block() (around line 2800)

#### 2. Apply truncation in _build_status_block()

Call _truncate_for_slack() on the formatted message before including it in the
Block Kit payload. This is the single chokepoint for all outbound messages,
so fixing it here prevents truncation issues everywhere.

#### 3. Update create_backlog_item() to return item metadata

Change create_backlog_item() to return a dict with filepath, filename, and
item_number instead of just the filepath string. This lets callers include
the item number in their notifications.

#### 4. Consolidate notifications in _run_intake_analysis()

Remove the duplicate notification from create_backlog_item() (the one that
says "Created {item_label} backlog item: {filename}"). Instead, have
_run_intake_analysis() send a single, comprehensive notification that includes:
- The item type and classification decision
- The title
- The root need (if available)
- The backlog item filename and number for reference

#### 5. Update INTAKE_ANALYSIS_PROMPT to request classification rationale

Add a "Classification:" field to the prompt so the LLM explains whether
the submission is truly a defect and why. Parse the result and include it
in the Slack response.

## Design Decisions

- Truncation at _build_status_block level ensures all outbound messages are safe,
  not just intake notifications. This is the architectural chokepoint.
- The 2900-char limit provides a 100-char safety margin for the emoji prefix
  that _build_status_block prepends.
- The duplicate notification removal means create_backlog_item() becomes a pure
  data operation that no longer sends Slack messages. The caller is responsible
  for notification, which is cleaner separation of concerns.
- Classification rationale is added to the LLM prompt rather than hardcoded
  rules, because the LLM already classifies during analysis and just needs
  to be explicit about it.
