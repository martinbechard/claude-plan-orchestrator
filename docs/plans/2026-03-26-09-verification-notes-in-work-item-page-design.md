# Design: Verification Notes on Work Item Detail Page

Feature: 09-verification-notes-in-work-item-page
Date: 2026-03-26

## Architecture Overview

Validation verdicts are produced by the `validate_task` executor node and stored
transiently on task dicts in the YAML plan. Today they never reach the completions
table or the `/item/<slug>` detail page.

This feature threads verification notes from the validator through the full pipeline
stack so they land in `completions.verification_notes` and are displayed on the
work item detail page.

### Data flow

```
validator agent
  → task-status.json  { verdict, message, findings[], evidence }
    → validate_task node
      → task["validation_findings"] (existing)
      → TaskState.plan_verification_notes  (NEW — JSON string of last verdict)
        → execute_plan.py returns verification_notes in state update
          → PipelineState.verification_notes  (NEW)
            → worker.py _write_result() includes verification_notes
              → supervisor.py reads it, passes to record_completion()
                → completions.verification_notes (NEW TEXT column)
                  → item.py passes parsed dict to template
                    → item.html Verification card
```

## verification_notes JSON schema

Stored as a compact JSON string in the `completions.verification_notes` column:

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

`evidence` is the raw validator output truncated to 4000 characters.
`findings` is a list of strings in `[PASS|WARN|FAIL] description` format.

## Key Files

### Modified

- `langgraph_pipeline/web/proxy.py`
  - Add `verification_notes TEXT` column to `completions` table (ALTER TABLE migration)
  - Add `verification_notes: Optional[str] = None` param to `record_completion()`
  - Update `list_completions_by_slug()` and `list_completions()` to include the column

- `.claude/agents/validator.md`
  - Require structured JSON output: `findings` array and `evidence` field in status file

- `langgraph_pipeline/executor/nodes/validator.py`
  - Update `_build_validator_prompt()` to request findings array and evidence in status JSON
  - Update `validate_task` to emit `plan_verification_notes` (JSON string of the last verdict)

- `langgraph_pipeline/executor/state.py`
  - Add `plan_verification_notes: Optional[str]` to `TaskState`

- `langgraph_pipeline/pipeline/state.py`
  - Add `verification_notes: Optional[str]` to `PipelineState`

- `langgraph_pipeline/pipeline/nodes/execute_plan.py`
  - Read `plan_verification_notes` from final executor state
  - Return it as `verification_notes` in the state update dict

- `langgraph_pipeline/worker.py`
  - Add `verification_notes: Optional[str]` param to `_write_result()`
  - Read `verification_notes` from `final_state`, include in result JSON

- `langgraph_pipeline/supervisor.py`
  - Read `verification_notes` from result dict
  - Pass to `record_completion()` at all three call sites

- `langgraph_pipeline/web/routes/item.py`
  - Parse `verification_notes` JSON from each completion record
  - Pass as `verifications` list to template

- `langgraph_pipeline/web/templates/item.html`
  - Add Verification card in the right column (below Completion History)
  - Show verdict badge (PASS/WARN/FAIL), findings list, collapsible evidence block

## Design Decisions

- **One notes record per completion**: verification notes are attached to the
  completion record, not stored separately. This keeps the schema minimal and
  ensures every completion has at most one verification snapshot.

- **JSON in TEXT column**: avoids a separate verifications table and complex
  joins. The data is read-only after write; no need for relational structure.

- **Only the final verdict per completion**: If a task was retried, only the
  verdict from the last validation attempt is stored (what ultimately passed).

- **Graceful degradation**: `verification_notes` is nullable. Old completions
  (before this feature) show "No verification data" rather than an error.

- **Evidence truncated at 4000 chars**: keeps the DB lean while still showing
  the most relevant output.
