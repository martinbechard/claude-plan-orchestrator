---
title: Cost Data Gaps in Traces — Design
date: 2026-03-26
defect: 22
---

# Cost Data Gaps in Traces — Design

## Problem

Only `execute_task` and `validate_task` nodes record `total_cost_usd` in their
trace metadata. Three other Claude-spawning nodes record no cost at all:

- `intake_analyze` (intake.py) — calls a local `_invoke_claude()` that uses raw
  `subprocess.run` without `--output-format json`, so no JSON result is returned.
- `verify_symptoms` (verification.py) — same pattern as intake.
- `create_plan` (plan_creation.py) — calls `_run_subprocess()` without
  `--output-format json`, so stdout is plain text and cost cannot be parsed.

Additionally, the `call_claude()` helper in `claude_cli.py` uses
`--output-format json` but `ClaudeResult` only returns `text` and
`failure_reason`. Cost is silently discarded. All Slack intake LLM calls
in `suspension.py` go through `call_claude` and have zero cost visibility.

## Architecture Overview

The cost data flows from the Claude CLI `result` event (in stream-json mode) or
the top-level JSON object (in `--output-format json` mode). Both include a
`total_cost_usd` field. The fix is to:

1. Add `total_cost_usd` to `ClaudeResult` and return it from `call_claude()`.
2. Switch local `_invoke_claude()` helpers in intake.py and verification.py to
   `--output-format json`, parse the JSON, and return cost alongside text.
3. Add `--output-format json` to `create_plan`'s planner command, parse the
   JSON response, and record cost in `add_trace_metadata`.
4. Update `add_trace_metadata` calls in all three pipeline nodes to include
   `total_cost_usd`.
5. Investigate the 0.01 pattern in execute_task: verify whether this is real
   low-cost reporting or a gap in the stream-json result-event capture.

## Key Files to Modify

- `langgraph_pipeline/shared/claude_cli.py` — extend `ClaudeResult` with
  `total_cost_usd`; update `call_claude()` to extract and return it.
- `langgraph_pipeline/pipeline/nodes/intake.py` — fix `_invoke_claude()` to
  use `--output-format json`, extract cost, and return it alongside text;
  include `total_cost_usd` in `add_trace_metadata` call.
- `langgraph_pipeline/pipeline/nodes/verification.py` — same fix as intake.py.
- `langgraph_pipeline/pipeline/nodes/plan_creation.py` — add
  `--output-format json` to planner command, parse cost from stdout, include
  `total_cost_usd` in `add_trace_metadata`.
- `langgraph_pipeline/slack/suspension.py` — record `total_cost_usd` from
  `ClaudeResult` in `add_trace_metadata` after each `call_claude` invocation
  (answer_question, _run_intake_analysis paths).
- `langgraph_pipeline/executor/nodes/task_runner.py` — audit the 0.01 pattern;
  confirm stream-json result-event capture is correct or fix if not.

## Design Decisions

- **`ClaudeResult` extension**: Add `total_cost_usd: float = 0.0` as a third
  named field. This is backward-compatible — existing callers that only use
  `.text` and `.failure_reason` are unaffected.
- **`--output-format json` for `--print` mode**: When Claude runs with
  `--print --output-format json`, stdout is a JSON object with `result` (the
  LLM text) and `total_cost_usd`. Parsing is one `json.loads` call.
- **`create_plan` subprocess**: The existing `_run_subprocess` captures stdout.
  Add `--output-format json` to the command and attempt JSON parse of stdout to
  extract cost. If parsing fails (e.g. mixed output), cost defaults to 0.0 —
  non-fatal.
- **Intake and verification `_invoke_claude()`**: Replace plain text capture
  with a small helper that returns `(text, cost_usd)` tuple. This avoids
  introducing a shared abstraction for a one-off pattern change.
- **Suspension.py**: Only the Slack-facing LLM calls need cost added to
  metadata — the `add_trace_metadata` calls should be placed immediately after
  each `call_claude` invocation in the three call sites.
- **0.01 investigation**: The `cost_usd` default in task_runner.py is 0.0, not
  0.01. If many rows show exactly 0.01, it may be an actual minimum charge from
  Claude for short sessions. The coder should verify by checking if Claude's
  stream-json output reliably populates `total_cost_usd` for all sessions or
  only above a certain duration/token threshold.
