# Trace observability gaps: capture subprocess errors, validator verdicts, and pipeline decisions

## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


## Status: Open

## Priority: High

## Summary

When investigating why item 21-intake-throttle was marked complete with only
1 of 3 tasks done, the traces DB could not answer basic diagnostic questions.
Five enhancements are needed so that future failures are fully diagnosable
from trace data alone.

## Background

Item 21 was processed 5 times. Run 1 spent $1.74 completing task 1.1 after
3 escalation cycles, then task 1.2's execute_task returned NULL cost/NULL
tool calls (Claude failed silently). Runs 2-5 all had $0.00 cost with NULL
execute_task results — Claude was not responding. After 5 warns the pipeline
archived the item as "completed" despite 2 of 3 tasks unfinished.

## Gap 1: Subprocess exit code and stderr in trace metadata

**Problem:** When call_claude or a Claude subprocess fails, the traces show
NULL cost and NULL tool_calls. There is no way to distinguish quota exhaustion
from timeout from API error from crash.

**Fix:** When recording an execute_task or validate_task trace, include in
metadata_json:
- subprocess_exit_code: int (0 = success, non-zero = failure)
- subprocess_error: str (first 500 chars of stderr on failure)
- failure_reason: str ("timeout" | "quota_exhausted" | "exit_code_N" | "ok")

## Gap 2: Validator verdict and findings in trace metadata

**Problem:** validate_task traces have cost but no record of what the
validator found. Was it PASS, WARN, or FAIL? What specific findings led
to the verdict? This is critical for understanding why items get retried
or archived.

**Fix:** Include in validate_task trace metadata:
- verdict: str ("PASS" | "WARN" | "FAIL")
- findings: list of strings (each finding from the validator)
- requirements_checked: int (count of requirements verified)
- requirements_met: int (count that passed)

This also relates to feature 09 (verification notes display).

## Gap 3: Pipeline decision rationale in traces

**Problem:** The pipeline makes decisions (retry, escalate, archive) that
are not recorded in traces. When an item is archived as "completed" with
warn outcomes, there is no trace of WHY — was it max retries? Max
verification cycles? Budget cap?

**Fix:** Add a pipeline_decision trace event (or metadata on the root run)
recording:
- decision: str ("retry" | "escalate" | "archive" | "skip")
- reason: str ("max_verification_cycles_reached" | "validator_passed" |
  "budget_exhausted" | etc.)
- cycle_number: int (which retry/verification cycle)
- tasks_completed: str (e.g. "1/3")

## Gap 4: Plan YAML state at each checkpoint

**Problem:** When looking at traces, we know task 1.1 was done but we
cannot see the plan YAML state — which tasks were marked done, which were
pending, what the task descriptions were.

**Fix:** At each execute_plan start and end, include a snapshot of the
plan task statuses in metadata:
- plan_tasks: list of {task_id, description, status} dicts
- completed_count: int
- total_count: int

## Gap 5: Distinguish "Claude returned empty" from "Claude never called"

**Problem:** execute_task traces with NULL cost could mean the subprocess
was called and returned empty, or it could mean the node short-circuited
without calling Claude at all (e.g. no more tasks to execute).

**Fix:** Add a metadata field:
- claude_invoked: bool (true if subprocess was spawned, false if skipped)
- skip_reason: str (if not invoked, why — "no_pending_tasks",
  "plan_complete", etc.)




## 5 Whys Analysis

Title: Why does the pipeline silently misfile incomplete items?
Clarity: 4
5 Whys:
1. Why was item 21 marked complete with only 1/3 tasks finished?
   → Because the pipeline hit max retry/warning cycles on runs 2-5 (NULL cost, NULL tool_calls) and archived it as abandoned work rather than continuing to investigate.

2. Why did max retries trigger an archive instead of escalation or investigation?
   → Because the pipeline couldn't diagnose whether the NULLs meant "Claude failed" (retry) vs "this node should be skipped" (continue) vs "something is broken upstream" (escalate).

3. Why can't the pipeline distinguish these failure modes?
   → The traces record only high-level outputs (cost, tool_calls) but omit process-level evidence: subprocess exit codes, stderr, validator findings, and node logic (was Claude called or not?).

4. Why does the trace system lack this diagnostic metadata?
   → It was designed to capture what Claude/tools output for observability, not the machinery around execution — the pipeline glue, decision points, and failure signals that infrastructure needs.

5. Why is this machinery-level visibility needed now?
   → Because incomplete-item misfiling looks identical to legitimate completion in the current traces; without post-mortem diagnosis capability, systemic bugs (like "validator returns FAIL but pipeline archives anyway") are invisible and unfixable.

Root Need: Post-mortem diagnosability of silent infrastructure failures from trace data alone, so that systemic pipeline bugs can be identified and fixed without re-running items.

Summary: The pipeline needs process-level and decision-level trace metadata to distinguish real completion from misfiling and to enable root-cause analysis of infrastructure failures after they occur.
