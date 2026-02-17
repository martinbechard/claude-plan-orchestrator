# Design: Enforce Complete 5 Whys Analysis in Intake Pipeline

## Date: 2026-02-17
## Defect: docs/defect-backlog/6-new-defect-when-a-defect-or-feature-is-received-the-agent-is-supposed-to-do-a.md
## Status: Revised (addressing verification #1 findings)

## Problem

When a defect or feature request is received via Slack, the agent runs a 5 Whys
analysis using an LLM call. However, the LLM sometimes returns only 1-2 Whys
instead of the required 5. The system accepts incomplete analyses without
validation and proceeds to create the backlog item.

## Prior Work (Task 1.1 - Completed)

The following changes are already in place in scripts/plan-orchestrator.py:
- Constants REQUIRED_FIVE_WHYS_COUNT=5 and MAX_INTAKE_RETRIES=1 (line 141-142)
- INTAKE_ANALYSIS_PROMPT strengthened with "MUST provide exactly 5" (line 149)
- INTAKE_RETRY_PROMPT defined (line 190) for retry attempts
- INTAKE_ANALYSIS_TIMEOUT_SECONDS=120 (line 218)
- _parse_intake_response() extracts five_whys list via regex (line 3695)

## Remaining Work (from Verification #1 Findings)

1. **Retry logic in _run_intake_analysis()** - The constants and retry prompt
   exist but are completely unused. The method must be modified to validate
   len(five_whys) and retry once if fewer than 5.

2. **Unit tests for retry behavior** - No tests exist for the validation/retry
   flow. Tests needed for: complete analysis (no retry), incomplete triggers
   retry, retry succeeds, retry fails (graceful degradation).

## Architecture

Call chain in plan-orchestrator.py:

```
_handle_inbound_feature/defect(msg)
  -> creates IntakeState
  -> _run_intake_analysis(intake)     # background thread
    -> _call_claude_print(INTAKE_ANALYSIS_PROMPT)   # LLM call
    -> _parse_intake_response(response)              # extracts fields
    -> [NEW] validate len(five_whys) >= REQUIRED_FIVE_WHYS_COUNT
    -> [NEW] if incomplete: retry with INTAKE_RETRY_PROMPT (up to MAX_INTAKE_RETRIES)
    -> [NEW] if still incomplete: log warning, proceed with available data
    -> create_backlog_item(...)                       # writes .md file
```

## Design: Retry Logic in _run_intake_analysis

After parsing the initial response (line ~3786), add a validation+retry block:

```python
# Validate 5 Whys completeness and retry if needed
if len(five_whys) < REQUIRED_FIVE_WHYS_COUNT:
    print(f"[INTAKE] Only {len(five_whys)} Whys returned, retrying...")
    retry_prompt = INTAKE_RETRY_PROMPT.format(
        count=len(five_whys),
        item_type=intake.item_type,
        text=intake.original_text,
        analysis=response_text,
    )
    retry_text = self._call_claude_print(
        retry_prompt, model="sonnet",
        timeout=INTAKE_ANALYSIS_TIMEOUT_SECONDS
    )
    if retry_text:
        retry_parsed = self._parse_intake_response(retry_text)
        if len(retry_parsed["five_whys"]) >= len(five_whys):
            # Retry produced equal or better results - use them
            parsed = retry_parsed
            response_text = retry_text
            title = parsed["title"] or fallback_title
            root_need = parsed["root_need"]
            five_whys = parsed["five_whys"]
            classification = parsed["classification"]
            description = parsed["description"] or response_text
            intake.analysis = response_text

if len(five_whys) < REQUIRED_FIVE_WHYS_COUNT:
    print(f"[INTAKE] WARNING: Only {len(five_whys)}/{REQUIRED_FIVE_WHYS_COUNT} Whys in final analysis")
```

The retry is inserted between the parse step (line 3786) and the "Enrich with 5 Whys
summary" step (line 3793). It reuses the existing constants and prompt template.

## Files Affected

| File | Change |
|------|--------|
| scripts/plan-orchestrator.py | Add retry logic in _run_intake_analysis after parsing |
| tests/test_plan_orchestrator.py | Add tests for 5 Whys retry behavior |

## Test Plan

Tests in tests/test_plan_orchestrator.py:

1. **test_intake_no_retry_when_five_whys_complete**: Mock _call_claude_print to
   return 5 Whys. Verify it is called exactly once (no retry).

2. **test_intake_retries_on_incomplete_whys**: Mock _call_claude_print to return
   2 Whys first, then 5 on retry. Verify retry happened and final backlog
   item includes all 5 Whys.

3. **test_intake_proceeds_after_failed_retry**: Mock _call_claude_print to return
   2 Whys both times. Verify backlog item is still created with 2 Whys
   (graceful degradation).

4. **test_intake_retry_uses_better_result**: Mock to return 2 Whys first, 4 on
   retry. Verify the 4-Why result is used (better than initial).

## Risks

- **Low**: Retry adds one extra LLM call per incomplete analysis. Runs in
  background thread so does not block main pipeline.
- **Low**: Worst-case analysis time doubles to ~4min. Acceptable for background.
- **None**: Graceful degradation ensures items are always created.
