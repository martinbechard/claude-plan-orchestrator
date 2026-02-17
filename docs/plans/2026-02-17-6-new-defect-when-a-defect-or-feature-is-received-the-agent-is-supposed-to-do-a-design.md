# Design: Enforce Complete 5 Whys Analysis in Intake Pipeline

## Date: 2026-02-17
## Defect: docs/defect-backlog/6-new-defect-when-a-defect-or-feature-is-received-the-agent-is-supposed-to-do-a.md
## Status: Draft

## Problem

When a defect or feature request is received via Slack, the agent runs a 5 Whys
analysis using an LLM call. However, the LLM sometimes returns only 1-2 Whys
instead of the required 5. The system accepts incomplete analyses without
validation and proceeds to create the backlog item.

The root cause is two-fold:
1. The prompt (INTAKE_ANALYSIS_PROMPT) asks for 5 Whys but does not strongly
   enforce it with explicit instructions about the minimum requirement
2. There is no post-parse validation that checks whether the LLM returned
   exactly 5 Whys before proceeding to backlog item creation

## Architecture Overview

The intake analysis flows through this call chain:

```
plan-orchestrator.py:
  _handle_inbound_feature/defect(msg)
    -> creates IntakeState
    -> _run_intake_analysis(intake)     # background thread
      -> _call_claude_print(INTAKE_ANALYSIS_PROMPT)   # LLM call
      -> _parse_intake_response(response)              # extracts fields
      -> create_backlog_item(...)                       # writes .md file
```

Key locations:
- INTAKE_ANALYSIS_PROMPT (line ~121): The prompt template for the LLM
- _parse_intake_response (line ~3568): Regex-based parser extracting five_whys list
- _run_intake_analysis (line ~3614): Orchestrates the analysis and creates the item

## Design Decision

### 1. Strengthen the prompt

Add explicit instructions to INTAKE_ANALYSIS_PROMPT emphasizing that all 5 Whys
are mandatory. Add a sentence like:

```
IMPORTANT: You MUST provide exactly 5 numbered "Why" questions and answers.
Do not stop at fewer than 5. Each Why should dig deeper into the previous answer.
```

### 2. Add validation with retry

After parsing the LLM response, check len(five_whys). If fewer than
REQUIRED_FIVE_WHYS_COUNT (5), retry the LLM call once with a more explicit
follow-up prompt that includes the incomplete analysis and asks for completion.

Constants:
- REQUIRED_FIVE_WHYS_COUNT = 5
- MAX_INTAKE_RETRIES = 1  (one retry for incomplete analysis)

### 3. Validation fallback

If the retry also fails to produce 5 Whys, proceed with whatever was returned
but log a warning. The backlog item is still valuable even with incomplete
analysis. The system should not block item creation over analysis depth.

## Files Affected

| File | Change |
|------|--------|
| scripts/plan-orchestrator.py | Strengthen INTAKE_ANALYSIS_PROMPT; add REQUIRED_FIVE_WHYS_COUNT constant; add retry logic in _run_intake_analysis; add INTAKE_RETRY_PROMPT constant |
| tests/test_slack_notifier.py | Add tests for 5 Whys validation: complete analysis, incomplete triggers retry, retry produces complete result, retry still incomplete proceeds with warning |
| tests/test_plan_orchestrator.py | Update existing _parse_intake_response tests if needed |

## Detailed Changes

### scripts/plan-orchestrator.py

1. Add constants near INTAKE_ANALYSIS_PROMPT:

```python
REQUIRED_FIVE_WHYS_COUNT = 5
MAX_INTAKE_RETRIES = 1
```

2. Strengthen INTAKE_ANALYSIS_PROMPT by adding an explicit enforcement line:

```python
INTAKE_ANALYSIS_PROMPT = """Analyze this {item_type} request using the 5 Whys method.

Request: {text}

Perform a 5 Whys analysis to uncover the root need behind this request.
IMPORTANT: You MUST provide exactly 5 numbered "Why" questions and answers. Do not stop at fewer than 5. Each Why should dig deeper into the root cause of the previous answer.
Then write a concise backlog item with a clear title and description.
Also classify whether this is truly a {item_type} or should be categorized differently.

Format your response exactly like this:
...
"""
```

3. Add a new retry prompt constant:

```python
INTAKE_RETRY_PROMPT = """Your previous 5 Whys analysis was incomplete - you only provided {count} out of 5 required Whys.

Original {item_type} request: {text}

Your previous analysis:
{analysis}

Please redo the analysis with EXACTLY 5 numbered Whys. Each Why must dig deeper into the previous answer to uncover the true root cause.

Format your response exactly like this:

Title: <one-line title for the backlog item>

Classification: <defect|feature|question> - <one sentence explaining why>

5 Whys:
1. <why>
2. <why>
3. <why>
4. <why>
5. <why>

Root Need: <the root need uncovered by the analysis>

Description:
<2-4 sentence description of the backlog item, incorporating the root need>
Keep it concise and actionable."""
```

4. In _run_intake_analysis, after parsing (line ~3655), add validation:

```python
# Validate 5 Whys completeness
if len(five_whys) < REQUIRED_FIVE_WHYS_COUNT and retry_count < MAX_INTAKE_RETRIES:
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
            parsed = retry_parsed
            response_text = retry_text
            # Re-extract fields from retry
            title = parsed["title"] or fallback_title
            root_need = parsed["root_need"]
            five_whys = parsed["five_whys"]
            classification = parsed["classification"]
            description = parsed["description"] or response_text
            intake.analysis = response_text

if len(five_whys) < REQUIRED_FIVE_WHYS_COUNT:
    print(f"[INTAKE] WARNING: Only {len(five_whys)}/{REQUIRED_FIVE_WHYS_COUNT} Whys in final analysis")
```

### tests/test_slack_notifier.py

Add tests:
- test_intake_analysis_retries_on_incomplete_whys: Mock LLM to return 2 Whys first, then 5 on retry. Verify retry happened and final item has 5 Whys.
- test_intake_analysis_proceeds_after_failed_retry: Mock LLM to return 2 Whys both times. Verify item is still created (graceful degradation).
- test_intake_analysis_no_retry_on_complete_whys: Mock LLM to return 5 Whys. Verify no retry call.

## Risks

- **Low**: The retry adds one additional LLM call per incomplete analysis. Since
  most analyses should complete correctly with the improved prompt, retries
  should be rare.
- **Low**: The retry timeout doubles the worst-case analysis time from 2min to
  4min. Acceptable since this runs in a background thread.
- **None**: Graceful degradation ensures items are always created even if
  analysis is incomplete.
