# Design: Quota Exhaustion Detection in intake_analyze and create_plan

## Overview

Extend the existing `detect_quota_exhaustion()` guard from `execute_task` to the two
upstream nodes (`intake_analyze`, `create_plan`) that also call Claude. When quota is
exhausted in these nodes, the item must stay on disk for re-discovery rather than
flowing forward to a spurious archive.

## Current Flow (broken)

```
scan_backlog  → [has_items] → intake_analyze
                                    ↓ (fixed edge — no quota check)
                              create_plan
                                    ↓ (fixed edge — no quota check)
                              execute_plan → [is_defect] → verify | archive
```

When quota is exhausted inside `intake_analyze` or `create_plan`, Claude returns an
empty or partial response. The fixed edges forward the item anyway. By the time the
pipeline reaches `is_defect()`, `quota_exhausted` is `False`, so the item is archived
with no work done.

## Target Flow (fixed)

```
scan_backlog  → [has_items] → intake_analyze
                                    ↓ [after_intake]
                              END (quota) | create_plan
                                               ↓ [after_create_plan]
                              END (quota) | execute_plan → [is_defect] → verify | archive
```

## Key Files to Modify

### `langgraph_pipeline/pipeline/nodes/intake.py`

- Import `detect_quota_exhaustion` from `langgraph_pipeline.shared.quota`.
- In `intake_analyze()`: after `_invoke_claude()` returns, pass the output to
  `detect_quota_exhaustion()`. If `True`, return `{"quota_exhausted": True}` immediately,
  skipping all further analysis and state updates.
- Apply the same check in `_verify_defect_symptoms()` and `_run_five_whys_analysis()`
  helpers (or check the raw output centrally in the node body).

### `langgraph_pipeline/pipeline/nodes/plan_creation.py`

- Import `detect_quota_exhaustion` from `langgraph_pipeline.shared.quota`.
- In `create_plan()`: after `_run_subprocess()` returns, call `detect_quota_exhaustion(combined_output)`.
  If `True`, return `{"quota_exhausted": True}` immediately (before the `_plan_exists` check).
  This mirrors the rate-limit guard already present above that path.

### `langgraph_pipeline/pipeline/edges.py`

Add two new routing functions:

```python
def after_intake(state: PipelineState) -> str:
    """Route from intake_analyze: END on quota, else create_plan."""
    if state.get("quota_exhausted"):
        return END
    return NODE_CREATE_PLAN

def after_create_plan(state: PipelineState) -> str:
    """Route from create_plan: END on quota, else execute_plan."""
    if state.get("quota_exhausted"):
        return END
    return NODE_EXECUTE_PLAN
```

Also add `NODE_EXECUTE_PLAN = "execute_plan"` constant to edges.py so routing
functions don't use bare strings.

### `langgraph_pipeline/pipeline/graph.py`

Replace fixed edges with conditional edges:

```python
# Before (broken):
graph.add_edge(NODE_INTAKE_ANALYZE, NODE_CREATE_PLAN)
graph.add_edge(NODE_CREATE_PLAN, NODE_EXECUTE_PLAN)

# After (fixed):
graph.add_conditional_edges(NODE_INTAKE_ANALYZE, after_intake)
graph.add_conditional_edges(NODE_CREATE_PLAN, after_create_plan)
```

Update the import from `edges.py` to include `after_intake` and `after_create_plan`.

## Test Files to Update

- `tests/langgraph/pipeline/test_edges.py`: add tests for `after_intake` and
  `after_create_plan` (quota → END, normal → next node).
- `tests/langgraph/pipeline/nodes/test_intake.py`: add test that `intake_analyze`
  returns `{"quota_exhausted": True}` when Claude output signals quota exhaustion.
- `tests/langgraph/pipeline/nodes/test_plan_creation.py`: add test that `create_plan`
  returns `{"quota_exhausted": True}` when subprocess output signals quota exhaustion.

## Design Decisions

- **No state schema change**: `quota_exhausted` already exists in `PipelineState`.
- **Mirror the rate-limit pattern**: `create_plan` already checks `is_rate_limited` from
  `check_rate_limit()`; quota detection is an analogous guard placed immediately after it.
- **Intake node check placement**: the quota check belongs in the node body (after the
  `_invoke_claude()` call) rather than inside each helper, keeping the helpers pure.
- **No retry in these nodes**: unlike rate limits which carry a reset time, quota
  exhaustion has no known reset — routing to END is the correct behavior (item stays
  on disk until the pipeline is restarted after quota refills).
