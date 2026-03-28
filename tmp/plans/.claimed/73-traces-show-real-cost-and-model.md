# Traces list: cost shows "—" and model shows "—" for most entries

## Summary

Cost and Model columns show "—" for most traces. Cost data exists in the
metadata_json (total_cost_usd) but is not being extracted. Model data is
inconsistent — some show "sonnet", most show nothing.

## Acceptance Criteria

- Does every completed trace row show a dollar cost (not "—")?
  YES = pass, NO = fail
- Does every trace row show the model used? YES = pass, NO = fail
- Is cost summed from all child runs for root traces?
  YES = pass, NO = fail

## LangSmith Trace: 3df2da47-4203-411d-bc30-fe97c9a0ac31


## 5 Whys Analysis

I'll analyze this defect using the 5 Whys method to uncover the underlying root cause.

---

**Title:** Traces list not displaying cost and model metrics from available backend data

**Clarity:** 4/5
The defect clearly identifies what's missing (cost and model columns), where data exists (metadata_json.total_cost_usd), and defines success criteria. It's slightly unclear whether this is missing extraction logic or missing API data retrieval.

**5 Whys:**

1. **Why are cost and model columns showing "—" instead of actual values?**
   → Because the traces list component is not extracting and rendering these values from the available backend data (metadata_json for cost, trace record for model).

2. **Why isn't the component extracting these values?**
   → Because the component implementation either lacks logic to parse metadata_json.total_cost_usd or lacks the model field retrieval/display in the rendering logic.

3. **Why was this parsing logic not implemented?**
   → Because the initial traces list feature was built without the requirement to display cost and model metrics—those features were deprioritized or discovered as needed after the MVP shipped.

4. **Why weren't cost and model display included in the initial implementation?**
   → Because the original scope focused on trace identity and execution status (name, status, timestamp) rather than operational metrics needed for cost tracking and model observability.

5. **Why is cost and model visibility now required?**
   → Because users and stakeholders need visibility into trace-level economics and model selection to make informed decisions about resource usage, cost optimization, and model suitability for different workloads.

**Root Need:** Teams need operational metrics (cost and model) at the trace list level to understand system economics, track model usage patterns, and make data-driven decisions about model selection and cost optimization.

**Summary:** The traces list MVP lacked cost/model visibility; now those metrics must be extracted from existing backend data and displayed to give users operational insight into trace execution economics.
