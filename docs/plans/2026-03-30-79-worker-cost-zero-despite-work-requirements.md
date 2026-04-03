# Structured Requirements: 79 Worker Cost Zero Despite Work

Source: tmp/plans/.claimed/79-worker-cost-zero-despite-work.md
Generated: 2026-03-30T16:35:43.365290+00:00

## Requirements

### P1: Worker reports $0.00 cost despite performing significant work
Type: functional
Priority: high
Source clauses: [C1, C2, C3, C6]
Description: The worker reads `session_cost_usd` from the final pipeline state to report cost (C3, C6). During the first execution of item 74-item-page-step-explorer, the pipeline ran for 25 minutes, executed intake analysis (clause extraction, 5 Whys), plan creation with validation, and multiple executor tasks (0.1, 0.2, 0.3, 1.1, 1.2), yet the completion record shows `cost_usd=0.0` (C2). The value the worker extracts from `final_state` is zero despite substantial API usage across multiple pipeline stages (C1).
Acceptance Criteria:
- After a pipeline run that performs intake, plan creation, and task execution, does the worker's reported cost reflect a non-zero value? YES = pass, NO = fail
- Does the cost value in the completion record match the sum of API costs incurred during the run? YES = pass, NO = fail

### P2: Cost accumulation breaks across pipeline node boundaries
Type: functional
Priority: high
Source clauses: [C4, C7, C8, C9]
Description: The pipeline has multiple independent nodes -- intake (C7), plan creation (C8), and executor (C9) -- that each track costs separately. Costs from early pipeline nodes (intake, requirements, plan creation) are not properly accumulated into `session_cost_usd` across node boundaries, or the accumulated value is reset when the executor subgraph runs (C4). The executor is a separate subgraph with its own state management, and the cost mapping logic in `execute_plan.py` may not merge executor costs with costs already accumulated from earlier nodes (C9). There is no consistent accumulation pattern merging costs from one node to the next.
Acceptance Criteria:
- After the intake node completes, does `session_cost_usd` in the pipeline state reflect the intake node's API costs? YES = pass, NO = fail
- After the plan creation node completes, does `session_cost_usd` include costs from both intake and plan creation? YES = pass, NO = fail
- After the executor subgraph completes, does `session_cost_usd` include costs from intake, plan creation, and all executor tasks combined? YES = pass, NO = fail
- Is the cost value monotonically non-decreasing across successive pipeline nodes (i.e., never reset to zero)? YES = pass, NO = fail

### FR1: Validated end-to-end cost accumulation across all pipeline stages
Type: functional
Priority: high
Source clauses: [C5, C7, C8, C9]
Description: The reported cost should reflect all API calls made during the worker's execution, including intake analysis, plan creation, validation, and task execution (C5). Each pipeline node -- intake (C7), plan creation (C8), and executor (C9) -- must contribute its incurred API costs to a running `session_cost_usd` total that is carried forward through the pipeline state. The executor subgraph must map its internal cost tracking back to the parent pipeline's `session_cost_usd` field, adding to (not replacing) any previously accumulated costs. A verification mechanism must ensure that cost accumulation works correctly end-to-end so that the final state value the worker reads is accurate.
Acceptance Criteria:
- Does each pipeline node (intake, plan creation, executor) add its costs to `session_cost_usd` rather than overwriting it? YES = pass, NO = fail
- Does the executor subgraph's cost mapping in `execute_plan.py` merge executor costs with pre-existing `session_cost_usd` from earlier nodes? YES = pass, NO = fail
- Is there a test that verifies `session_cost_usd` accumulates correctly through intake, plan creation, and execution stages? YES = pass, NO = fail
- For a run that performs intake, plan creation, and task execution, does the final `session_cost_usd` equal the sum of costs from all stages? YES = pass, NO = fail

---

## Coverage Matrix
| Raw Input Section | Requirement(s) |
|---|---|
| Title: "Worker reports $0.00 cost despite performing work" | P1 |
| Execution details (25 min, stages, tasks, cost_usd=0.0) | P1 |
| Root cause hypothesis (costs not accumulated, reset by executor) | P2 |
| Expected behavior (cost should reflect all API calls) | FR1 |
| Affected code: worker.py cost extraction | P1 |
| Affected code: intake.py cost accumulation | P2, FR1 |
| Affected code: plan_creation.py cost accumulation | P2, FR1 |
| Affected code: execute_plan.py cost mapping | P2, FR1 |
| LangSmith trace reference | P1 (diagnostic context) |
| 5 Whys W1-W2: session_cost_usd is 0 in final state | P1 |
| 5 Whys W3: no consistent accumulation across nodes | P2 |
| 5 Whys W4: executor subgraph doesn't propagate costs back | P2 |
| 5 Whys W5: no end-to-end verification of cost flow | FR1 |
| 5 Whys Root Need: validated cost accumulation | FR1 |

## Clause Coverage Grid
| Clause | Type | Mapped To | Status |
|---|---|---|---|
| C1 [C-PROB] | PROB | P1 | Mapped |
| C2 [C-FACT] | FACT | P1 | Mapped |
| C3 [C-FACT] | FACT | P1 | Mapped |
| C4 [C-PROB] | PROB | P2 | Mapped |
| C5 [C-GOAL] | GOAL | FR1 | Mapped |
| C6 [C-FACT] | FACT | P1 | Mapped |
| C7 [C-FACT] | FACT | P2, FR1 | Mapped |
| C8 [C-FACT] | FACT | P2, FR1 | Mapped |
| C9 [C-FACT] | FACT | P2, FR1 | Mapped |
| C10 [C-CTX] | CTX | P1 | Mapped (diagnostic trace context for P1 investigation) |

## Validation

Status: ACCEPTED
Iterations: 1
Reviewer notes: ACCEPT


## Acceptance Criteria

**AC1**: After a pipeline run that performs intake analysis, plan creation, and task execution, does the worker report a non-zero `cost_usd` in the completion record? YES = pass, NO = fail
  Origin: Derived from C1 [PROB] (inverse: "$0.00 cost despite work" -> "cost is non-zero after work")
  Belongs to: P1
  Source clauses: [C1, C2]

**AC2**: Does the worker extract `session_cost_usd` from the final pipeline state and use that value as the reported `cost_usd` in the completion record? YES = pass, NO = fail
  Origin: Derived from C3 [FACT] (mechanism verification)
  Belongs to: P1
  Source clauses: [C3, C6]

**AC3**: After the intake node completes, does `session_cost_usd` in the pipeline state contain a non-zero value reflecting the intake node's API costs? YES = pass, NO = fail
  Origin: Derived from C4 [PROB] (inverse: "costs not accumulated across boundaries" -> "cost is present after first boundary")
  Belongs to: P2
  Source clauses: [C4, C7]

**AC4**: After the plan creation node completes, does `session_cost_usd` in the pipeline state reflect the cumulative cost of both intake and plan creation (i.e., greater than or equal to the value after intake alone)? YES = pass, NO = fail
  Origin: Derived from C4 [PROB] (inverse: "costs not accumulated" -> "costs accumulate across nodes")
  Belongs to: P2
  Source clauses: [C4, C7, C8]

**AC5**: After the executor subgraph completes, does `session_cost_usd` in the pipeline state include costs from intake, plan creation, and all executor tasks combined (i.e., greater than or equal to the value after plan creation)? YES = pass, NO = fail
  Origin: Derived from C4 [PROB] (inverse: "reset when executor subgraph ran" -> "executor adds to rather than resets cost")
  Belongs to: P2
  Source clauses: [C4, C9]

**AC6**: Is `session_cost_usd` monotonically non-decreasing across successive pipeline node completions (i.e., the value never decreases or resets to zero between nodes)? YES = pass, NO = fail
  Origin: Derived from C4 [PROB] (inverse: "accumulated value is reset" -> "value never resets")
  Belongs to: P2
  Source clauses: [C4]

**AC7**: Does each pipeline node (intake, plan creation, executor) add its incurred costs to the existing `session_cost_usd` value rather than overwriting it? YES = pass, NO = fail
  Origin: Derived from C5 [GOAL] (operationalized: "reflect all API calls" -> "each node adds, not overwrites")
  Belongs to: FR1
  Source clauses: [C5, C7, C8, C9]

**AC8**: Does the executor subgraph's cost mapping in `execute_plan.py` merge executor costs with the pre-existing `session_cost_usd` from earlier nodes (additive merge, not replacement)? YES = pass, NO = fail
  Origin: Derived from C5 [GOAL] (operationalized: "reflect all API calls including task execution" -> "executor merges costs additively")
  Belongs to: FR1
  Source clauses: [C5, C9]

**AC9**: Is there a test that verifies `session_cost_usd` accumulates correctly through intake, plan creation, and execution stages in sequence, with the final value equaling the sum of all stages? YES = pass, NO = fail
  Origin: Derived from C5 [GOAL] (operationalized: "should reflect all API calls" -> "verified via automated test")
  Belongs to: FR1
  Source clauses: [C5, C7, C8, C9]

**AC10**: For a complete pipeline run that performs intake, plan creation, and task execution, does the final `session_cost_usd` value (as read by the worker) equal the sum of costs individually reported by each stage? YES = pass, NO = fail
  Origin: Derived from C5 [GOAL] (operationalized: end-to-end sum equality check)
  Belongs to: FR1
  Source clauses: [C5, C3, C6]

---

## Requirement -> AC Coverage

| Requirement | ACs | Count |
|---|---|---|
| P1 | AC1, AC2 | 2 |
| P2 | AC3, AC4, AC5, AC6 | 4 |
| FR1 | AC7, AC8, AC9, AC10 | 4 |

## Clause -> AC Coverage

| Clause | Type | AC | How |
|---|---|---|---|
| C1 | PROB | AC1 | Inverse ("$0.00 despite work" -> "non-zero after work") |
| C2 | FACT | AC1 | Provides the test scenario for AC1 (25-min run with multiple stages) |
| C3 | FACT | AC2, AC10 | Mechanism under test: worker reads session_cost_usd from final state |
| C4 | PROB | AC3, AC4, AC5, AC6 | Inverse ("not accumulated / reset" -> "accumulated and never reset") |
| C5 | GOAL | AC7, AC8, AC9, AC10 | Made testable: "should reflect all" -> additive merge + sum equality + test exists |
| C6 | FACT | AC2, AC10 | Identifies code location (worker.py) verified by AC2 extraction check and AC10 end-to-end |
| C7 | FACT | AC3, AC4, AC7, AC9 | Identifies code location (intake.py) verified by intake cost presence and additive pattern |
| C8 | FACT | AC4, AC7, AC9 | Identifies code location (plan_creation.py) verified by cumulative cost and additive pattern |
| C9 | FACT | AC5, AC7, AC8, AC9 | Identifies code location (execute_plan.py) verified by executor merge and additive pattern |
| C10 | CTX | -- | Diagnostic trace reference for investigation; not directly testable as an AC |
