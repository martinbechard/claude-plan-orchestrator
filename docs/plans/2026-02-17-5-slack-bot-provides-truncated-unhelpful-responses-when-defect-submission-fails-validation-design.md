# Design: Fix Slack Bot Truncated/Unhelpful Responses on Defect Submission

## Problem

When defects are submitted via Slack, the bot provides truncated, incomplete
responses that lack:
1. Message length enforcement (Slack Block Kit sections have a 3000-char limit)
2. Backlog item ID and filename reference in the confirmation message
3. Clear classification feedback explaining why the submission was classified
   as a defect vs feature

## Current State

The production code in scripts/plan-orchestrator.py has been fixed:

- _truncate_for_slack() helper added at line 2808, using SLACK_BLOCK_TEXT_MAX_LENGTH = 2900
- create_backlog_item() now returns a dict with filepath/filename/item_number
- _run_intake_analysis() now builds comprehensive notifications with item
  references, classification, and root need

However, 6 unit tests in tests/test_slack_notifier.py are broken because
their mocks still return strings instead of the new dict return type.

## Architecture Overview

All changes are in scripts/plan-orchestrator.py within the SlackNotifier class.
The remaining work is purely in tests/test_slack_notifier.py.

### Key Files

- scripts/plan-orchestrator.py - Production code (already fixed)
- tests/test_slack_notifier.py - 6 failing tests that need mock updates

### Broken Tests and Required Fixes

#### Group 1: Tests that call create_backlog_item() directly (3 tests)

These tests call the real create_backlog_item() and assert on the string
return value. They must be updated to use the dict return type:

1. test_create_backlog_feature (line 1178)
   - Change: assert on result['filepath'] instead of result directly
   - Verify: os.path.exists(result['filepath']), 'item_number' key exists

2. test_create_backlog_defect (line 1242)
   - Change: assert 'defect-backlog' in result['filepath']
   - Verify: os.path.exists(result['filepath'])

3. test_create_backlog_numbering (line 1294)
   - Change: os.path.basename(result['filepath']) for filename check

#### Group 2: Tests that mock create_backlog_item() for intake analysis (3 tests)

These tests provide mock_create that returns a string. The mock must return
a dict matching the real return type:

4. test_intake_analysis_clear_request (line 1892)
   - Change mock return to: {"filepath": "docs/feature-backlog/1-test.md",
     "filename": "1-test.md", "item_number": 1}

5. test_intake_analysis_unstructured_response (line 1954)
   - Change mock return to: {"filepath": "docs/defect-backlog/1-test.md",
     "filename": "1-test.md", "item_number": 1}

6. test_intake_empty_response_creates_fallback (line 2083)
   - Change mock return to: {"filepath": "docs/feature-backlog/1-test.md",
     "filename": "1-test.md", "item_number": 1}

## Design Decisions

- Truncation at _build_block_payload level ensures all outbound messages
  are safe, not just intake notifications
- The 2900-char limit provides a 100-char safety margin for the emoji prefix
- create_backlog_item() returning a dict is cleaner than returning a string
  and parsing it - callers get structured access to item_number and filename
- Classification rationale uses LLM analysis rather than hardcoded rules
