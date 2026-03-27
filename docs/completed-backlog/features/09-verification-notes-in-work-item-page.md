# Display validator verification notes on work item detail page

## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


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




## 5 Whys Analysis

Title: Display validator verification notes on work item detail page

Clarity: 4

5 Whys:

1. **Why is this feature needed?** The validator agent produces verification notes but they are not being stored or displayed to users, so users cannot see what checks were performed or what the validator concluded about an item's completion status.

2. **Why aren't the notes being stored and displayed?** Currently there is no database schema to persist verification notes and no UI component to render them on the work item detail page. The validator output exists but is not captured in the completions table or surfaced in the frontend.

3. **Why is persistence of verification notes critical?** Without persistent storage, verification notes are lost when the pipeline restarts. Users lose the audit trail of what was validated, making it impossible to review why an item was marked complete or to re-examine a validator decision.

4. **Why do users need to review validator decisions?** The validator is an automated system that could have incomplete checks, false positives, or edge cases it misses. Users need to audit validator findings to catch incorrect completions before they propagate downstream and degrade data quality.

5. **Why does auditing validator decisions matter for this project?** This project is tracking work item completions through automated validation. If users cannot see what the validator checked, they lose trust in completion statuses and cannot distinguish between legitimate passes and false positives, undermining the entire validation system's credibility.

Root Need: Users need transparent, persistent audit records of what the validator checked so they can verify correctness of automated completions and maintain trust in the work tracking system.

Summary: The validator must produce and persist structured verification notes so users can review and audit validator decisions on every work item.
