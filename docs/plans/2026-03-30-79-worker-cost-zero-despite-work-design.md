# Design: 79 Worker Cost Zero Despite Work

Source item: tmp/plans/.claimed/79-worker-cost-zero-despite-work.md
Requirements: docs/plans/2026-03-30-79-worker-cost-zero-despite-work-requirements.md

## Architecture Overview

The pipeline graph runs items through a sequence of nodes:
intake_analyze -> structure_requirements -> create_plan -> execute_plan -> verify_fix -> archive

Each node spawns Claude CLI calls that incur API costs. These costs are tracked
locally within each node function (as total_cost_usd) but are never propagated
into the pipeline state's session_cost_usd field. The worker reads
session_cost_usd from the final pipeline state to report cost in the completion
record.

The bug has two dimensions:
1. Four nodes (intake_analyze, structure_requirements, create_plan, verify_fix)
   compute costs but do not include session_cost_usd in their return dicts.
2. execute_plan returns session_cost_usd but starts from 0.0 without reading
   the existing accumulated value from state. Since session_cost_usd is a plain
   float (no LangGraph reducer annotation), the return value replaces rather
   than adds to any prior accumulation.

The same problem affects session_input_tokens and session_output_tokens.

The fix is straightforward: each node must read the current session_cost_usd
from state, add its own incurred costs, and return the accumulated total. The
worker extraction logic (worker.py line 322) is correct and needs no changes.

## Key Files to Modify

- langgraph_pipeline/pipeline/nodes/intake.py - Include session_cost_usd in state_updates
- langgraph_pipeline/pipeline/nodes/requirements.py - Include session_cost_usd in return dict
- langgraph_pipeline/pipeline/nodes/plan_creation.py - Include session_cost_usd in return dict
- langgraph_pipeline/pipeline/nodes/execute_plan.py - Add executor cost to existing session_cost_usd
- langgraph_pipeline/pipeline/nodes/verification.py - Include session_cost_usd in return dict
- tests/langgraph/pipeline/nodes/test_cost_accumulation.py - New test for end-to-end accumulation

## Design Decisions

### D1: Additive cost accumulation pattern in each pipeline node
- Addresses: P1, P2, FR1
- Satisfies: AC1, AC2, AC3, AC4, AC5, AC6, AC7, AC10
- Approach: Each pipeline node that incurs API costs must follow this pattern:
  1. Read the current accumulated cost: prior_cost = state.get("session_cost_usd", 0.0)
  2. Track its own costs as total_cost_usd (already done in all nodes)
  3. Return session_cost_usd: prior_cost + total_cost_usd in the state update dict
  This ensures costs accumulate monotonically across node boundaries. The same
  pattern applies to session_input_tokens and session_output_tokens where the
  node tracks token usage.
  Affected nodes:
  - intake_analyze: add session_cost_usd to state_updates dict
  - structure_requirements: add session_cost_usd to return dict
  - create_plan: add session_cost_usd to return dict
  - verify_fix: add session_cost_usd to return dict
- Files:
  - langgraph_pipeline/pipeline/nodes/intake.py (modify)
  - langgraph_pipeline/pipeline/nodes/requirements.py (modify)
  - langgraph_pipeline/pipeline/nodes/plan_creation.py (modify)
  - langgraph_pipeline/pipeline/nodes/verification.py (modify)

### D2: Additive merge in execute_plan for executor subgraph costs
- Addresses: P2, FR1
- Satisfies: AC5, AC6, AC8, AC10
- Approach: execute_plan currently returns session_cost_usd: cost_usd where
  cost_usd comes solely from the executor subgraph (plan_cost_usd). The fix
  reads the existing session_cost_usd from the pipeline state (which now
  includes intake + requirements + plan_creation costs from D1) and adds the
  executor's cost to it. This makes the executor merge additive rather than
  a replacement. The same fix applies to session_input_tokens and
  session_output_tokens.
- Files:
  - langgraph_pipeline/pipeline/nodes/execute_plan.py (modify)

### D3: End-to-end cost accumulation test
- Addresses: FR1
- Satisfies: AC9
- Approach: Create a test that mocks the Claude CLI calls in each pipeline node
  to return known cost values, runs the pipeline through intake -> requirements
  -> plan_creation -> execute_plan, and verifies that session_cost_usd in the
  final state equals the sum of all individual node costs. The test verifies
  monotonic non-decrease across node transitions and that the final value
  matches the expected sum. This test goes in a new file dedicated to cost
  accumulation to avoid bloating existing test files.
- Files:
  - tests/langgraph/pipeline/nodes/test_cost_accumulation.py (create)

## Design -> AC Traceability Grid

| AC | Design Decision(s) | Approach |
|---|---|---|
| AC1 | D1 | All nodes propagate costs; worker reads non-zero session_cost_usd from final state |
| AC2 | D1 | Worker extraction (state.get("session_cost_usd")) unchanged; value is now correct |
| AC3 | D1 | intake_analyze adds its total_cost_usd to session_cost_usd in state_updates |
| AC4 | D1 | create_plan reads prior session_cost_usd and adds its own total_cost_usd |
| AC5 | D1, D2 | execute_plan adds executor plan_cost_usd to existing session_cost_usd |
| AC6 | D1, D2 | Each node reads prior value and adds (never replaces); value is monotonically non-decreasing |
| AC7 | D1, D2 | The pattern is prior + own = returned; every node adds, none overwrites |
| AC8 | D2 | execute_plan reads state["session_cost_usd"] and adds plan_cost_usd to it |
| AC9 | D3 | Dedicated test verifies sum equality across intake, requirements, plan_creation, execution |
| AC10 | D1, D2 | Final session_cost_usd equals sum of all individual node costs |
