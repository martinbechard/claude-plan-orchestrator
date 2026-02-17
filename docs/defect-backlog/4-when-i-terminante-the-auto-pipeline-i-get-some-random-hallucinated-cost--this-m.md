# when I terminante the auto-pipeline, I get some random hallucinated cost -this m

## Status: Open

## Priority: Medium

## Summary

Aha! So the cost data is REAL - these are actual API calls made by Claude Code! The user's confusion stems from thinking "I use Claude Code" means "it's free" but Claude Code actually makes API calls under the hood and incurs costs.

Now let me perform the 5 Whys analysis:

**Title:** Remove misleading cost reporting for Claude Code usage

**5 Whys:**

1. **Why does the user want to remove cost data?**
   Because they see "$3.7144" cost reports when terminating auto-pipeline and believe this data is "hallucinated" or fake.

2. **Why do they think the cost data is fake?**
   Because they believe "I use Claude Code" means no API costs should be incurred, but the pipeline is showing dollar amounts.

3. **Why is there a mismatch between expectations and reality?**
   Because the user doesn't realize that Claude Code (when invoked programmatically via `claude --print`) still makes API calls to Anthropic's backend and incurs costs - it's not a local-only tool.

4. **Why is the cost reporting confusing rather than informative?**
   Because the code doesn't explain the source of costs or clarify that Claude Code usage equals API usage - it just shows dollar amounts without context.

5. **Why doesn't the reporting provide proper context?**
   Because the usage tracking was designed assuming users understand that all Claude invocations (whether via Code, API, or CLI) incur costs - there's no educational messaging about this.

**Root Need:** The user needs transparency about whether costs being reported are real API costs or placeholder/estimated values, and clarity about when Claude Code usage translates to API billing.

**Description:**

The cost reporting in auto-pipeline sessions displays actual API costs from Claude Code invocations, but users may mistakenly believe these are fabricated numbers because they associate "Claude Code" with a free desktop tool rather than an API-backed service. The reporting should either: (1) add context explaining these are real API costs from Claude Code's backend calls, (2) suppress cost reporting entirely when usage data is unavailable or zero, or (3) clearly distinguish between estimated vs actual costs. The root issue is lack of transparency about the source and nature of the cost data being displayed.

## Source

Created from Slack message by U0AEWQYSLF9 at 1771305204.414029.

## Verification Log

### Verification #1 - 2026-02-17 01:00

**Verdict: FAIL**

**Checks performed:**
- [x] Build passes (py_compile on both scripts succeeds)
- [x] Unit tests pass (157 passed in 1.92s)
- [x] Old bare "Total cost:" removed from auto-pipeline.py (no matches found)
- [x] "API-Equivalent Estimates" header in auto-pipeline.py (line 560)
- [ ] "API-Equivalent Estimates" header in plan-orchestrator.py (MISSING - still says "Usage Summary" at line 580)
- [x] "not actual subscription charges" context in auto-pipeline.py (line 561)
- [ ] "not actual subscription charges" context in plan-orchestrator.py format_final_summary (MISSING from format_final_summary; exists only in unrelated context at line 3483)
- [x] Zero-cost guard in auto-pipeline.py (line 1687: if session_tracker.work_item_costs)
- [x] Tilde prefix on costs in auto-pipeline.py (lines 554, 570)
- [ ] Tilde prefix on costs in plan-orchestrator.py (MISSING - lines 569, 572, 581, 595 all use bare "$" amounts)
- [ ] Old "Total cost:" removed from plan-orchestrator.py (STILL PRESENT at line 581)

**Findings:**
auto-pipeline.py has been fully updated per the plan (Task 1.1 completed). All cost output shows "API-Equivalent Estimates" header, "not actual subscription charges" context, tilde-prefixed amounts, and the zero-cost guard is in place.

plan-orchestrator.py has NOT been updated (Task 1.2 still pending in the YAML plan). The format_summary_line() method (line 558) still uses bare "$" amounts without tilde prefix. The format_final_summary() method (line 575) still uses the old "Usage Summary" header and "Total cost:" label without "API-Equivalent" context. No tilde prefixes on per-section or per-task cost amounts.

The reported symptom (confusing cost display without context) is partially resolved: auto-pipeline.py now provides proper context, but plan-orchestrator.py still shows bare cost amounts without qualifying text. Since both scripts can display cost information to users, the fix is incomplete.
