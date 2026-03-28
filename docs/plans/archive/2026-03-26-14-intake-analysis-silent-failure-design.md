# Design: Intake Analysis Silent Failure

## Problem

When `call_claude()` fails during Slack intake analysis, the failure is invisible:
- `call_claude()` in `claude_cli.py` logs a WARNING (truncated to 200 chars) and returns `""`
- `_run_intake_analysis_inner()` in `suspension.py` sees `""`, creates the item from raw text, and sends "Analysis unavailable, created from raw text" with no explanation
- `add_error()` is never called, so the dashboard Error Stream stays empty
- Quota exhaustion is not checked before attempting the intake call

## Architecture Overview

Three coordinated changes:

1. **`call_claude()` returns a failure reason** — change the return type to a
   `NamedTuple` (`ClaudeResult`) carrying both the response text and an optional
   `failure_reason` string. Existing callers that only inspect the text field are
   unaffected (they get `result.text`). The `probe_quota_available()` helper is
   updated to use the new type.

2. **`_run_intake_analysis_inner()` exposes failures** — after a failed
   `call_claude()` call, read `result.failure_reason`, call
   `get_dashboard_state().add_error()`, and embed the reason in the Slack fallback
   message. Also gate the call on `probe_quota_available()` so quota-exhausted
   states are detected before spawning a doomed subprocess.

3. **Tests updated** — `test_suspension.py` mocks updated to return `ClaudeResult`;
   new tests assert `add_error()` is called and the Slack message contains the
   failure reason.

## Key Files

| File | Change |
|------|--------|
| `langgraph_pipeline/shared/claude_cli.py` | Add `ClaudeResult` NamedTuple; change `call_claude()` to return it with `failure_reason` on error |
| `langgraph_pipeline/shared/quota.py` | Update `probe_quota_available()` to use `ClaudeResult.text` |
| `langgraph_pipeline/slack/suspension.py` | Gate intake on quota check; call `add_error()` and embed reason in Slack message on failure |
| `tests/langgraph/slack/test_suspension.py` | Update mocks and add failure-path tests |
| `tests/langgraph/shared/test_claude_cli.py` | Add tests for `ClaudeResult` failure paths |

## Design Decisions

- **`NamedTuple` over raising exceptions** — `call_claude()` is called in
  fire-and-forget contexts (Q&A, dedup) where a raised exception would be
  unhandled. A structured return keeps the existing call sites working without
  changes while giving intake the failure reason it needs.

- **Full stderr, not 200-char truncation** — the truncation was arbitrary and
  discarded the most informative part of error messages. Full stderr is now
  captured in `failure_reason`.

- **Quota gate in `_run_intake_analysis_inner()`** — quota state lives in the
  supervisor; the Slack handler has no direct access. The gate uses
  `probe_quota_available()` (already used by the scan loop) so no new shared
  state is introduced.

- **`add_error()` is best-effort** — wrapped in `try/except` so a dashboard
  state unavailability (e.g. in tests) does not break the intake flow.

- **Slack message format** — failure reason is appended as a parenthetical:
  `_(Analysis unavailable: quota exhausted — created from raw text)_`. This
  matches the existing style of the fallback message.

## Backwards Compatibility

`call_claude()` callers that only used the return value as a boolean or string
will need to use `result.text` instead. The signature change is internal
(not part of any public API). `PollerCallbacks.call_claude` type annotation
is updated to accept `(prompt, model, timeout) -> ClaudeResult`.
