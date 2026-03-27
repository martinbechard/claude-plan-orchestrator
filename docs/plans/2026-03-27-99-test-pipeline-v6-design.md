# Test: Full Pipeline with YAML Rescue - Design

## Overview

End-to-end pipeline test that verifies the YAML rescue mechanism works correctly
when Claude Code blocks writes to `.claude/` directories. The test adds a comment
to `langgraph_pipeline/shared/paths.py` and confirms the pipeline completes with
rescue logging and non-zero cost.

## Key Files

| File | Change |
|------|--------|
| `langgraph_pipeline/shared/paths.py` | Add comment `# yaml rescue test` |

## Acceptance Criteria

1. `langgraph_pipeline/shared/paths.py` contains `# yaml rescue test`
2. Pipeline log shows "Rescued YAML plan from permission denial"
3. Item completes with non-zero cost

## Design Decisions

- Single task: this is a simple code change (add one comment line) followed by
  pipeline-level verification handled by the orchestrator's built-in validator
- The coder agent reads the work item directly for full context
