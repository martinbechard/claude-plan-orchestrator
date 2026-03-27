# Design: Trace Observability Gaps

## Overview

Five trace metadata enhancements to make pipeline failures fully diagnosable from
trace data alone. The backlog item is marked "Review Required" -- some gaps were
previously implemented and need verification, others need new work.

## Current State

Based on code analysis, the following already exist in the codebase:

- **Gap 1 (subprocess errors):** execute_task already records subprocess_exit_code,
  subprocess_error, and failure_reason in trace metadata.
- **Gap 2 (validator verdicts):** validate_task already records verdict, findings,
  requirements_checked, and requirements_met.
- **Gap 5 (claude_invoked):** execute_task already records claude_invoked: True/False.

The following are NOT yet implemented:

- **Gap 3 (pipeline decisions):** No trace metadata for retry/escalate/archive
  decisions in pipeline edges or nodes.
- **Gap 4 (plan state snapshots):** No plan task status snapshot in execute_plan
  start/end metadata.

## Key Files to Modify

### Gap 3: Pipeline Decision Rationale

- langgraph_pipeline/pipeline/edges.py -- verify_result() and route_after_execution()
  make archive/retry decisions but do not emit trace metadata
- langgraph_pipeline/executor/edges.py -- retry_check() and circuit_check() make
  retry/escalate decisions without trace metadata
- langgraph_pipeline/executor/escalation.py -- escalate_model() decisions not traced

### Gap 4: Plan State Snapshots

- langgraph_pipeline/pipeline/nodes/execute_plan.py -- execute_plan() invokes the
  executor subgraph; should snapshot plan task statuses at start and end

## Design Decisions

1. Use existing add_trace_metadata() for all new metadata -- consistent with current pattern
2. Pipeline decision traces go on the edge/node that makes the decision
3. Plan snapshots are lightweight: list of {task_id, status} dicts plus counts
4. All existing Gap 1/2/5 implementations need verification against the spec, not reimplementation

## Implementation Approach

Section 1 verifies existing implementations (Gaps 1, 2, 5) match the spec.
Section 2 implements missing functionality (Gaps 3, 4).
