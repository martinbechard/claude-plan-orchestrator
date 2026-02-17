# Design: Clarify Cost Reporting as API-Equivalent Estimates

## Problem

When a user terminates the auto-pipeline (Ctrl+C), the session usage summary
prints raw dollar amounts like "$3.7144" without any context. Users on Claude
Code Max subscriptions interpret these as "hallucinated" costs because they
believe Claude Code is free. In reality, these are API-equivalent cost estimates
reported by the Claude CLI - not actual charges.

## Current State (after Verification #1)

auto-pipeline.py has been fully fixed:
- "API-Equivalent Estimates" header in SessionUsageTracker.format_session_summary()
- "not actual subscription charges" context line
- Tilde prefix (~$) on per-item costs
- Zero-cost guard suppresses summary when no work items completed

plan-orchestrator.py is NOT yet fixed. The PlanUsageTracker class still uses:
- "Usage Summary" header (should say "API-Equivalent Estimates")
- "Total cost:" label without "API-Equivalent" qualifier
- Bare "$" amounts without tilde prefix in format_summary_line() and format_final_summary()
- No "(not actual subscription charges)" context line

## Remaining Work

### 1. Update format_summary_line() in plan-orchestrator.py (line 558)

Change per-task usage lines from:
  [Usage] Task {id}: ${cost} | ... | Running: ${total}
to:
  [Usage] Task {id}: ~${cost} | ... | Running: ~${total}

### 2. Update format_final_summary() in plan-orchestrator.py (line 575)

Change the final summary block from:
  === Usage Summary ===
  Total cost: ${cost}
to:
  === Usage Summary (API-Equivalent Estimates) ===
  (These are API-equivalent costs reported by Claude CLI, not actual subscription charges)
  Total API-equivalent cost: ~${cost}

Also add tilde prefix to per-section cost lines.

### 3. Add regression tests for plan-orchestrator cost formatting

Test that format_summary_line() and format_final_summary() output contains:
- Tilde prefix (~$) on all cost amounts
- "API-Equivalent" in the final summary header
- "not actual subscription charges" context line

## Files to Modify

- scripts/plan-orchestrator.py - PlanUsageTracker.format_summary_line(), PlanUsageTracker.format_final_summary()
- tests/test_plan_orchestrator_usage.py - regression tests for cost formatting

## Design Decisions

1. Use "API-equivalent" rather than "estimated" to be precise about what the number represents
2. Use tilde prefix (~$) on all cost amounts for visual distinction from actual charges
3. Add "(not actual subscription charges)" qualifier in the summary header only, not on every line
4. Match the formatting pattern already established in auto-pipeline.py for consistency
