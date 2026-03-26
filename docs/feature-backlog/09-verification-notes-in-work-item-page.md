# Display validator verification notes on work item detail page

## Status: Open

## Priority: High

## Summary

The validator agent should produce verification notes (what was checked, what
passed, what was flagged) for every item it processes. These notes need to be:

1. Persisted alongside the completion record so they survive pipeline restarts.
2. Displayed on the work item detail page (/item/<slug>) so the user can see
   exactly what the validator checked and what it concluded.

Currently there is no mechanism to store or display these notes. If the
validator is already producing them (writing to a status file), they are not
surfaced in the UI. If the validator is not producing them, the validator
protocol needs to be enhanced to require structured verification output.

## Expected Behavior

### Validator Output
The validator agent should write a structured verification report including:
- Verdict: PASS / WARN / FAIL
- Findings: list of checks performed with pass/warn/fail per check
- Evidence: command output, file references, or code snippets supporting
  each finding

### Persistence
Store the verification report in the completions table (new column
`verification_notes TEXT`) or in a separate `verifications` table linked by
slug. The report should be written at the same time the completion is recorded.

### Work Item Detail Page
The /item/<slug> page should include a "Verification" section showing:
- The verdict badge (PASS/WARN/FAIL)
- The list of findings with severity
- Collapsible evidence blocks

### Validator Protocol Enhancement
If the validator is not already producing structured output, update
`.claude/agents/validator.md` to require the agent to write its report in a
machine-parseable format (e.g. JSON or structured markdown) that the
supervisor can read and store.

## Dependencies

- Feature 06: work item detail page (where notes are displayed)
- Defect 19: validator marks incomplete work as done (related — better
  notes would make false completions visible)
