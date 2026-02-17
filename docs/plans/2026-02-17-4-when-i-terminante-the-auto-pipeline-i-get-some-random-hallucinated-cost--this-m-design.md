# Design: Clarify Cost Reporting in Auto-Pipeline

## Problem

When a user terminates the auto-pipeline (Ctrl+C), the session usage summary
prints raw dollar amounts like "$3.7144" without any context. Users on Claude
Code Max subscriptions interpret these as "hallucinated" costs because they
believe Claude Code is free. In reality, these are API-equivalent cost estimates
reported by the Claude CLI - not actual charges.

The plan-orchestrator.py already has contextual labeling in two places:
- The Slack Q&A system prompt (line 105-107) explains these are API-equivalent estimates
- The _format_state_context method (line 3482-3483) labels costs as "API-equivalent cost ... not actual subscription charges"

But auto-pipeline.py's SessionUsageTracker.format_session_summary() has no such
context - it prints "Total cost: $X.XXXX" without qualification.

## Root Cause

SessionUsageTracker.format_session_summary() in auto-pipeline.py (line 558-570)
formats cost data without any clarifying label. Users see bare dollar amounts
and assume they are being charged.

## Solution

### 1. Add "API-equivalent estimate" context to all cost output in auto-pipeline.py

Modify SessionUsageTracker.format_session_summary() to:
- Change header from "Pipeline Session Usage" to include "API-Equivalent" qualifier
- Add a one-line explanation below the header
- Change "Total cost:" to "API-equivalent cost:" throughout

### 2. Add context to per-item usage log lines

Modify the log line in record_from_report() (line 554) from:
  "[Usage] {name}: ${cost:.4f}"
to:
  "[Usage] {name}: ~${cost:.4f} (API-equivalent)"

### 3. Suppress summary when no costs were tracked

If the session tracker has zero work items and zero cost, skip printing the
summary entirely. This handles the case where the user terminates before any
work item completes (which would show a confusing "$0.0000" line).

### 4. Add context to PlanUsageTracker in plan-orchestrator.py

Apply the same "API-equivalent" labeling to:
- format_summary_line() per-task output
- format_final_summary() final summary header

This ensures consistency between both scripts.

## Files to Modify

- scripts/auto-pipeline.py - SessionUsageTracker class (format_session_summary, record_from_report)
- scripts/plan-orchestrator.py - PlanUsageTracker class (format_summary_line, format_final_summary)
- tests/test_auto_pipeline.py or new test file - regression tests

## Design Decisions

1. Use "API-equivalent" rather than "estimated" to be precise about what the number represents
2. Keep dollar formatting as-is ($X.XXXX) since the values are real API-equivalent costs
3. Suppress zero-cost summaries entirely to avoid confusion on early termination
4. Add the "(not actual subscription charges)" qualifier only in the summary header, not on every line, to keep log output concise
