# Read-Only Analysis Task Workflow

## Status: Open

## Priority: Medium

## Depends On: 16-least-privilege-agent-sandboxing

## Summary

Add a new task workflow type for read-only analysis tasks that produce reports
instead of code changes. Examples include documentation reviews, full test suite
reports, code audits, dependency checks, and architecture assessments.

These tasks differ from feature/defect work in that they never modify project
code, require no verification loop, and deliver a structured report as their
output.

## New Backlog Type

Add a new backlog directory: docs/analysis-backlog/

Analysis items follow a simpler format than feature/defect items:
- Summary of what to analyze
- Scope (which files/directories/aspects to cover)
- Output format (Slack message, markdown report, or both)

## Workflow Differences from Feature/Defect

| Aspect | Feature/Defect | Analysis |
|--------|---------------|----------|
| Agent permissions | Write-capable | Read-only only |
| Plan structure | Multi-phase (architect, coder, reviewer, verifier) | Single-phase (analyzer) |
| Output | Code changes + commit | Structured report |
| Verification loop | Build + test after each task | None needed |
| Slack channel | features/defects | New: orchestrator-reports |

## Agent Selection

Analysis tasks use read-only agents only:
- code-explorer for codebase analysis
- code-reviewer for code quality audits
- qa-auditor for test coverage reports
- e2e-analyzer for test result analysis
- spec-verifier for spec compliance checks

The orchestrator picks the agent based on the analysis type specified in the
backlog item.

## Report Delivery

Analysis results are delivered as:
1. A Slack message summary in the orchestrator-reports channel
2. Optionally, a full markdown report saved to docs/reports/

## Integration with Auto-Pipeline

The auto-pipeline scan loop should check docs/analysis-backlog/ in addition to
the existing feature and defect backlogs. Analysis items are processed with the
lighter workflow — no plan YAML needed, no verification cycles.

## Acceptance Criteria

- Analysis backlog directory is scanned by the pipeline
- Analysis tasks run with read-only agent permissions (depends on feature 16)
- Reports are delivered via Slack and/or saved to docs/reports/
- No project files are modified during analysis task execution
- Pipeline correctly distinguishes analysis items from feature/defect items
