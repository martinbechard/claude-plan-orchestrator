# Design: Graceful Quota-Exhaustion Handling

**Work item:** docs/feature-backlog/01-detect-when-were-out-of-quota-in-claude-code-and-dont-process-any-further-ite.md
**Date:** 2026-03-24

---

## Overview

Add a system-wide LLM-availability circuit breaker that detects Claude Code quota
exhaustion, pauses the pipeline safely, and auto-resumes when the LLM becomes
available again. Quota exhaustion is distinguished from rate limiting: rate limits
carry a parseable reset time; quota exhaustion does not.

---

## Architecture

### Detection

Quota exhaustion is detected inside `task_runner.py`'s `_run_claude()` function, where
the full Claude CLI stdout/stderr is available. The new `langgraph_pipeline/shared/quota.py`
module provides the detection logic. It reuses `check_rate_limit()` from `rate_limit.py`:
if that function returns `(True, None)` (rate-limited but no parseable reset time), the
pipeline treats the situation as quota exhaustion and enters probe mode.

### State propagation

`quota_exhausted: bool` is added to both `TaskState` (executor subgraph) and
`PipelineState` (pipeline graph). When the task runner detects quota exhaustion it:

1. Resets the task's status back to `pending` in the plan YAML (so the item is not
   permanently marked failed and will be retried when the pipeline resumes).
2. Returns `{"quota_exhausted": True}` from the executor node.

`execute_plan.py` maps `TaskState.quota_exhausted` into `PipelineState.quota_exhausted`.

### Routing change

`edges.py` modifies `is_defect()` to check `quota_exhausted` first: if True, it returns
`END` (skipping `verify_symptoms` and `archive`), leaving the backlog item untouched so
the scan loop will re-select it after quota restores.

### Probe-based idle loop

The CLI scan loop in `cli.py` checks `final_state.get("quota_exhausted")` after each
graph invocation. When True, it calls `_run_quota_probe_loop()`, which sleeps for
`QUOTA_PROBE_INTERVAL_SECONDS` (300 s / 5 minutes) between lightweight `call_claude()`
probes. On a successful probe the loop returns and the normal scan loop resumes.
SIGINT/SIGTERM remain honoured during the probe sleep.

---

## Key files

| Action | File |
|--------|------|
| Create | `langgraph_pipeline/shared/quota.py` |
| Modify | `langgraph_pipeline/executor/state.py` — add `quota_exhausted` field |
| Modify | `langgraph_pipeline/pipeline/state.py` — add `quota_exhausted` field |
| Modify | `langgraph_pipeline/executor/nodes/task_runner.py` — detect quota, reset task |
| Modify | `langgraph_pipeline/pipeline/nodes/execute_plan.py` — propagate field |
| Modify | `langgraph_pipeline/pipeline/edges.py` — route to END on quota_exhausted |
| Modify | `langgraph_pipeline/cli.py` — quota probe loop |
| Create | `tests/langgraph/shared/test_quota.py` |

---

## Design decisions

**Reuse `check_rate_limit()`**: Quota exhaustion is the `(True, None)` case — rate
limited but with no parseable reset. This avoids duplicating pattern matching and
keeps the two failure modes distinguished by a single predicate.

**Reset task to pending (not failed)**: A quota-exhausted task is not a task-level
failure. Marking it pending preserves correct retry semantics and prevents the
circuit breaker from tripping on infrastructure unavailability.

**Route to END (not archive)**: Skipping archive keeps the backlog item on disk so
the scan loop re-discovers it automatically after quota restores. No manual
intervention is needed.

**Probe with `call_claude()`**: A minimal prompt ("Reply with only the word OK")
sent via the existing `call_claude()` helper is cheap, observable, and reuses all
the existing subprocess/env setup without adding a new code path.

**Single probe interval constant**: `QUOTA_PROBE_INTERVAL_SECONDS = 300` in
`quota.py`. Five minutes balances responsiveness against unnecessary LLM calls
while the account is still exhausted.
