# Validator agent marks incomplete work as completed

## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


## Status: Open

## Priority: High

## Summary

Work items are being marked as "completed" and archived even when the
implementation is only partially done. The cost analysis feature (03) was
archived as successful but the DB contained only fake test data, the /analysis
page showed dummy entries (foo.py, "12-test-item"), and the tool-call duration
histogram explicitly said "not yet available". The validator passed it anyway.

## Root Cause (suspected)

The validator agent prompt (`.claude/agents/validator.md`) checks:
1. Build passes
2. Unit tests pass
3. E2E tests (if referenced)
4. Code review (file headers, no any types, etc.)
5. Requirements from the work item file

Step 5 ("verify each requirement is satisfied") is the critical gate, but the
validator may be interpreting requirements too loosely. For example, the
acceptance criterion "/analysis displays real data after at least one worker
completes" was likely not tested against the running system — the validator
probably just checked that the code path existed, not that real data flowed
through it.

Specific weaknesses in the current validator:
- Does not verify end-to-end data flow (e.g. does real data actually appear?)
- Does not distinguish test fixtures from real data
- Does not check for placeholder/dummy content in the UI
- May be using Sonnet instead of Opus (now fixed to Opus)
- Does not verify that "not yet available" notes in the UI correspond to
  incomplete requirements

## Expected Behavior

The validator should:
1. Verify functional requirements against the running system, not just code
   existence.
2. Flag any "not yet available", "TODO", or placeholder text as incomplete.
3. Check that test data was cleaned up and real data can flow through.
4. Report WARN or FAIL when acceptance criteria involve end-to-end
   verification that cannot be confirmed by reading code alone.

## Suggested Fix

1. Update `.claude/agents/validator.md` to explicitly instruct the agent:
   - Search for TODO, "not yet available", placeholder, test/dummy data in
     output pages and flag as WARN.
   - For acceptance criteria involving "displays X" or "shows Y", attempt to
     verify against the running server if possible, or flag as WARN with
     "cannot verify at validation time — requires runtime confirmation".
   - Never pass an item where acceptance criteria explicitly mention end-to-end
     behavior if the validator can only confirm code-level changes.

2. Consider adding a two-stage validation: code review (can be done offline)
   and runtime verification (requires running server + real data flow).




## 5 Whys Analysis

**Title:** Validator accepts incomplete features because it can only verify code, not runtime functionality

**Clarity:** 4

**5 Whys:**

1. Why was incomplete work marked as completed?
   The validator checked that code compiled, tests passed, and code style was correct, but did not verify that acceptance criteria were actually satisfied when the system ran with real data.

2. Why didn't the validator verify acceptance criteria with real data?
   Because the validator uses static code analysis and offline tests to avoid requiring a running system, but the acceptance criteria (e.g., "/analysis displays real data") inherently require observing the system at runtime with actual data flowing through it.

3. Why was the validator designed to work without a running system when some acceptance criteria require runtime observation?
   Because the work item definitions did not distinguish between "code must exist and compile" criteria (verifiable offline) versus "feature must work end-to-end" criteria (requiring runtime), so the validator couldn't tell which type each criterion was.

4. Why wasn't there an explicit distinction between offline and runtime criteria in work item definitions?
   Because the validation framework was designed to be fully automated and scale without human judgment or external system access, making it impossible for the validator to know when to escalate uncertainty back to a human.

5. Why was automation without escalation paths built into the validation process?
   To enable fast, consistent validation that could run independently on every completed item without requiring a developer to manually test or system access to verify, but this prevented the validator from handling criteria that genuinely require runtime verification.

**Root Need:** Establish a clear protocol in work item definitions that distinguishes offline-verifiable criteria (code correctness, unit tests) from runtime-verifiable criteria (data flow, UI state), and empower the validator to fail or warn when acceptance criteria require runtime verification that cannot be performed offline.

**Summary:** The validator marks work complete based on offline checks (code/tests) without realizing some acceptance criteria require runtime verification against a live system with real data.
