# Slack intake: "analysis unavailable" with no diagnostic information

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

When a user submits a defect or feature via Slack, the response is sometimes
"analysis unavailable, created from raw text" with no explanation of what went
wrong. The underlying call_claude() failure is completely invisible — no error
in the dashboard, no Slack message with the reason, no way to diagnose or
retry intelligently.

## Root Cause

call_claude() in claude_cli.py silently returns "" on any failure:
- subprocess.TimeoutExpired  → logs WARNING, returns ""
- proc.returncode != 0       → logs WARNING with stderr[:200], returns ""
- json.JSONDecodeError       → logs WARNING, returns ""

The WARNING is emitted to the Python logger. Since defect 10 (error stream
always empty) means pipeline warnings never reach the dashboard, and the
pipeline stdout/stderr go to a closed pipe, there is no way to know what
actually failed.

## Likely Causes (in order of probability)

1. Quota exhausted — pipeline workers may have just consumed all quota when
   the Slack intake tried to run its own call_claude. The quota probe only
   blocks the scan loop, not the Slack intake handler.
2. Timeout — INTAKE_ANALYSIS_TIMEOUT_SECONDS = 120 may not be enough when
   Opus is slow or quota is recovering.
3. Transient API error — non-zero exit code from claude CLI due to network or
   API error; actual error text is truncated to 200 chars and discarded.

## Expected Behavior

- The Slack response should include the failure reason (e.g. "analysis failed:
  quota exhausted — item created from raw text, will not be re-analyzed").
- The dashboard error stream should receive an add_error() call with the
  failure detail.
- call_claude() should capture and return the full stderr on failure, or at
  minimum log it without truncation.
- The intake handler should check if quota is exhausted before attempting
  call_claude(), and queue the analysis for retry when quota recovers.

## Fix

1. In call_claude(), log full stderr (not just 200 chars) and expose the
   failure reason to callers (e.g. return a named tuple or raise instead of
   returning "").
2. In _run_intake_analysis(), call get_dashboard_state().add_error() with
   the failure detail when call_claude returns empty.
3. Include the failure reason in the Slack fallback message.
4. Gate the intake call_claude on quota availability (check
   probe_quota_available() before calling, or share the quota state with
   the Slack handler).




## 5 Whys Analysis

**Title:** Lack of error visibility prevents users from understanding why Slack intake analysis fails

**Clarity:** 5

**5 Whys:**

1. **Why is "analysis unavailable" without diagnostic details unhelpful to users?**
   Because they can't distinguish between recoverable failures (quota exhausted, retry later) and permanent ones (malformed input, etc.), so they can't decide whether to resubmit, escalate, or accept the fallback raw-text item.

2. **Why doesn't the Slack response include the actual failure reason?**
   Because the intake handler only receives an empty string from `call_claude()` — there's no information passed back about *what* went wrong, just that something did.

3. **Why doesn't `call_claude()` communicate the failure reason to its caller?**
   Because it treats all errors identically (timeout, quota, API error, JSON parse) and returns empty string in every case, discarding the underlying error context that would let callers respond appropriately.

4. **Why does error information get logged to the Python logger but never reach users or the dashboard?**
   Because the logging layer is disconnected from the user communication paths — logs go to a closed pipe (defect 10), and there's no error propagation contract between `call_claude()` and the intake handler to forward diagnostics to Slack or dashboard.

5. **Why does the system lack an error propagation and classification layer?**
   Because the abstraction boundaries were drawn without considering that different failure types need different handling: quota exhaustion needs retry logic, timeouts need deadline adjustment, and transient API errors need user communication — but all three currently fail silently and look identical to the user.

**Root Need:** The system needs structured error propagation with classification — failures must surface through the call stack with enough context for each layer (subprocess → Python → handler → user) to make appropriate decisions and communicate meaningfully with users about why operations failed and what to do next.

**Summary:** Users can't diagnose or respond to analysis failures because error information is lost at multiple boundaries in the system, leaving them with a meaningless fallback message instead of actionable diagnostic feedback.
