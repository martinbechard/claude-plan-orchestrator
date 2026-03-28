# Design: Insufficient Context Validation for Intake Messages

## Problem

The intake pipeline in plan-orchestrator.py processes any Slack message into a
backlog item without checking whether it contains enough context to be actionable.
Messages like "try again" create defect items that cannot be investigated or resolved.

## Architecture Overview

Add a context-sufficiency quality gate between message receipt and backlog item
creation. The gate uses the existing LLM intake analysis to detect low-context
messages and leverages the existing suspension mechanism to ask clarifying questions
via Slack instead of creating an unactionable backlog item.

### Flow Change

```
Current:  Slack msg -> LLM analysis -> create backlog item (always)
Proposed: Slack msg -> LLM analysis -> quality check -> create item OR ask for clarification
```

## Key Files to Modify

- **scripts/plan-orchestrator.py** - Main changes:
  - Modify INTAKE_ANALYSIS_PROMPT to include a clarity rating (1-5 scale)
  - Modify _parse_intake_response() to extract the clarity rating
  - Add context validation in _run_intake_analysis_inner() after parsing
  - On low clarity: send a Slack reply asking for more detail instead of
    creating a backlog item
  - Add minimum message length check in _handle_polled_messages()

- **tests/test_agent_identity.py** or new test file - Tests for:
  - Clarity rating parsing from LLM response
  - Low-context message detection and Slack reply behavior
  - Minimum length filter
  - Normal messages still processed correctly

## Design Decisions

1. **LLM-based quality scoring over heuristics**: A simple length check catches
   the most trivial cases, but "fix the thing" is long enough to pass a length
   check while still being unactionable. The LLM analysis already runs; adding
   a clarity rating costs nothing extra.

2. **Clarification reply over silent drop**: When a message lacks context, reply
   in-thread asking for specifics rather than silently ignoring. This teaches
   users what good submissions look like.

3. **Threshold**: Clarity < 3 (out of 5) triggers clarification request.
   This is conservative - only clearly insufficient messages are caught.

4. **No suspension files for intake**: Unlike work-item suspensions, intake
   clarifications use simple Slack thread replies. The user can reply with
   more context which gets picked up as a new message in the same channel.
   This keeps the implementation simple.

## Constants to Add

- MINIMUM_INTAKE_MESSAGE_LENGTH = 20 (characters)
- INTAKE_CLARITY_THRESHOLD = 3 (minimum clarity score to proceed)
- INTAKE_CLARIFICATION_TEMPLATE - message asking user for more context
