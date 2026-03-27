# Design: Verification Notes on Work Item Detail Page

Feature: 09-verification-notes-in-work-item-page
Date: 2026-03-27

## Architecture Overview

Validation verdicts are produced by the validator agent and saved as JSON files in
docs/reports/worker-output/{slug}/. The work item page already loads and displays
these file-based results via _load_validation_results(). However, verification notes
are not persisted in the completions table, so they are not tied to specific
completion records and lack structured findings/evidence.

This feature threads structured verification notes (verdict, findings, evidence)
from the validator through the pipeline state into the completions table, then
displays them on the work item detail page as part of each completion record.

### Data flow

```
validator agent
  writes tmp/task-status.json { verdict, message, findings[], evidence }
    validate_task node reads it
      sets TaskState.plan_verification_notes (JSON string)
        execute_plan.py returns verification_notes in state update
          PipelineState.verification_notes (new field)
            worker.py _write_result() includes verification_notes
              supervisor.py reads it, passes to record_completion()
                completions.verification_notes (new TEXT column)
                  item.py parses JSON, passes to template
                    item.html Verification card per completion
```

## verification_notes JSON schema

Stored as compact JSON in completions.verification_notes TEXT column:

```json
{
  "verdict": "PASS",
  "findings": [
    "[PASS] Build succeeded",
    "[PASS] Tests: 42 passed",
    "[WARN] Missing type annotation at foo.py:42"
  ],
  "evidence": "$ pnpm build\n> exit 0\n..."
}
```

evidence is truncated to 4000 characters. findings uses [PASS|WARN|FAIL] prefix format.

## Key Files

### Modified

- langgraph_pipeline/web/proxy.py
  - Add verification_notes TEXT column via ALTER TABLE migration
  - Add verification_notes param to record_completion()
  - Include column in list_completions_by_slug() and list_completions()

- .claude/agents/validator.md
  - Require structured JSON output: findings array and evidence field in status file

- langgraph_pipeline/executor/nodes/validator.py
  - Update _build_validator_prompt() to request findings array and evidence
  - Emit plan_verification_notes (JSON string) from validate_task

- langgraph_pipeline/executor/state.py
  - Add plan_verification_notes: Optional[str] to TaskState

- langgraph_pipeline/pipeline/state.py
  - Add verification_notes: Optional[str] to PipelineState

- langgraph_pipeline/pipeline/nodes/execute_plan.py
  - Read plan_verification_notes from final executor state
  - Return as verification_notes in state update dict

- langgraph_pipeline/worker.py
  - Include verification_notes from final_state in result JSON

- langgraph_pipeline/supervisor.py
  - Read verification_notes from result dict, pass to record_completion()

- langgraph_pipeline/web/routes/item.py
  - Parse verification_notes JSON from completion records
  - Pass structured data to template alongside existing validation_results

- langgraph_pipeline/web/templates/item.html
  - Add Verification Notes section per completion showing verdict badge,
    findings list, and collapsible evidence block

## Design Decisions

- One notes record per completion: verification notes attach to the completion
  record, not stored separately. Every completion has at most one verification.

- JSON in TEXT column: avoids separate table and joins. Data is write-once, read-only.

- Only final verdict per completion: if a task was retried, only the last
  validation attempt's verdict is stored.

- Graceful degradation: verification_notes is nullable. Old completions show
  "No verification data" instead of errors.

- Evidence truncated at 4000 chars: keeps DB lean while showing relevant output.

- Complements existing validation_results: the file-based validation results
  (from _load_validation_results) remain for backward compatibility. The new
  verification_notes provide per-completion structured data.
