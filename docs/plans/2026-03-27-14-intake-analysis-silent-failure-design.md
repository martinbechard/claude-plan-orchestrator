# Design: Intake Analysis Silent Failure

## Problem

When call_claude() fails during Slack intake analysis, the failure is invisible:
no error in the dashboard, no Slack message with the reason, no way to diagnose.

The defect spans two layers:
1. Slack intake (suspension.py) -- the original defect scope
2. Pipeline intake node (intake.py) -- _call_llm() callers must handle 3-tuple

## Current State

A prior implementation addressed the Slack intake layer (items 1-4 from the defect Fix section):

1. call_claude() returns ClaudeResult NamedTuple with failure_reason (full stderr)
2. _run_intake_analysis_inner() calls add_error() on failure
3. Slack fallback message includes the failure reason
4. Quota gate via probe_quota() before attempting call_claude()

The pipeline intake node (intake.py) also needs _call_llm() callers fixed to
unpack the 3-tuple (text, cost, failure_reason) and handle failures.

## Key Files

| File | Role |
|------|------|
| langgraph_pipeline/shared/claude_cli.py | ClaudeResult NamedTuple, call_claude() with structured error returns |
| langgraph_pipeline/slack/suspension.py | Quota gate, add_error(), failure reason in Slack message |
| langgraph_pipeline/pipeline/nodes/intake.py | _call_llm() callers must unpack 3-tuple; add_error(); quota gate |
| tests/langgraph/shared/test_claude_cli.py | Tests for ClaudeResult failure paths |
| tests/langgraph/slack/test_suspension.py | Tests for Slack intake failure handling |
| tests/langgraph/pipeline/nodes/test_intake.py | Tests for pipeline intake failure paths |

## Design Decisions

- NamedTuple over exceptions: call_claude() is used in fire-and-forget contexts
- Full stderr capture: no 200-char truncation
- add_error() wrapped in try/except: dashboard unavailability must not break intake
- Quota gate uses existing probe_quota_available() -- no new shared state
- No retry logic in intake nodes -- pipeline orchestrator handles retries at task level

## Acceptance Criteria

- call_claude() returns ClaudeResult with failure_reason on all error paths
- All _call_llm() callers in intake.py unpack and check failure_reason
- _run_intake_analysis_inner() calls add_error() with failure detail
- Slack message includes failure reason text
- Quota check gates intake calls (both Slack and pipeline)
- Error strings are never appended as analysis to backlog files
- Tests cover failure paths in claude_cli.py, suspension.py, and intake.py
