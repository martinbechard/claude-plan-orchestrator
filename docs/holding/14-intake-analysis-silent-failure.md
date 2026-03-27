# Slack intake: "analysis unavailable" with no diagnostic information

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

## LangSmith Trace: cb193a87-4711-4eee-b74f-75a67e64c9dc
