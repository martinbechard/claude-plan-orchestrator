# Design: Slack Intake Acknowledgment with Analysis Summary

## Date: 2026-02-17
## Feature: docs/feature-backlog/5-new-enhancement-when-accepting-the-feature-via-slack-you-need-to-acknowledge-w.md
## Status: Draft

## Problem

When a user submits a feature request or defect via Slack, the system silently
starts a background analysis thread and produces no output until the backlog item
is created (2+ minutes later). The user has no confirmation that their message
was received, and no chance to verify the system understood their intent before
work begins.

## Goal

Add a two-phase acknowledgment flow:

1. **Immediate acknowledgment** - sent as soon as the intake thread starts,
   confirming the message was received and analysis is underway.
2. **Analysis summary** - sent after the 5 Whys analysis completes but before
   creating the backlog item, showing the system's interpretation (title,
   classification, root need, 5 Whys summary) so the user can verify alignment.

## Architecture

Current call chain in plan-orchestrator.py:

```
_handle_polled_messages(messages)
  -> creates IntakeState (line 3943)
  -> spawns thread -> _run_intake_analysis(intake)  (line 3953)
    -> _call_claude_print(INTAKE_ANALYSIS_PROMPT)   (line 3758)
    -> _parse_intake_response(response)             (line 3781)
    -> [validate 5 Whys + retry if needed]          (line 3789-3815)
    -> create_backlog_item(...)                      (line 3830)
    -> send_status(success notification)            (line 3845)
```

Enhanced call chain:

```
_handle_polled_messages(messages)
  -> creates IntakeState (line 3943)
  -> spawns thread -> _run_intake_analysis(intake)
    -> [NEW] send_status("Analyzing your request...") - immediate ack
    -> _call_claude_print(INTAKE_ANALYSIS_PROMPT)
    -> _parse_intake_response(response)
    -> [validate 5 Whys + retry if needed]
    -> [NEW] send_status(analysis summary message) - shows understanding
    -> create_backlog_item(...)
    -> send_status(success notification - existing)
```

## Design Details

### 1. Immediate Acknowledgment

At the top of _run_intake_analysis(), before the LLM call, send a brief
info-level message to the originating channel:

```python
self.send_status(
    f"*Received your {intake.item_type} request.* Analyzing...",
    level="info", channel_id=intake.channel_id,
)
```

This uses the existing send_status() infrastructure. Level "info" renders with
:large_blue_circle: emoji.

### 2. Analysis Summary Message

After the 5 Whys analysis completes (and retry if needed), before creating the
backlog item, send a summary showing the system's interpretation:

```python
INTAKE_ACK_TEMPLATE = """*Here is my understanding of your {item_type}:*

*Title:* {title}
*Classification:* {classification}
*Root need:* {root_need}

_Creating backlog item..._"""
```

This is sent at level "info" to the originating channel. It provides a
checkpoint where the user can see exactly what the system understood.

### 3. New Constant

Add INTAKE_ACK_TEMPLATE near the other INTAKE_* constants (after line 218).

### 4. Error Path

The immediate acknowledgment is best-effort. If send_status() fails (e.g.,
Slack API error), the analysis continues. The acknowledgment must not block
the analysis pipeline.

## Files Affected

| File | Change |
|------|--------|
| scripts/plan-orchestrator.py | Add INTAKE_ACK_TEMPLATE constant; add two send_status() calls in _run_intake_analysis() |
| tests/test_plan_orchestrator.py | Add tests for acknowledgment messages |

## Test Plan

1. **test_intake_sends_immediate_ack**: Verify send_status is called with
   "Received your feature request" before the LLM call.

2. **test_intake_sends_analysis_summary**: Verify send_status is called with
   the analysis summary (title, classification, root need) after analysis but
   before create_backlog_item.

3. **test_intake_ack_on_empty_response**: Verify the immediate ack is still
   sent even when the LLM returns empty (the early-return path at line 3763).

4. **test_intake_ack_on_analysis_error**: Verify the immediate ack is sent
   even when the analysis raises an exception.

## Risks

- **Low**: Two extra Slack API calls per intake. Runs in background thread.
- **None**: Acknowledgment is fire-and-forget; failures do not affect analysis.
- **Low**: Adds ~50ms latency before the LLM call for the first send_status().
