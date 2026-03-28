# Design: Update 10 Medium-Priority Design Docs

## Overview

Update 10 design documents that contain stale references to the old
plan-orchestrator.py architecture. Each document needs specific corrections
as identified in the audit report (docs/reports/design-doc-audit.md) under
"Recommended Next Steps: UPDATE Documents -- Medium Priority".

## Files to Modify

All files are in docs/plans/:

1. 2026-02-16-11-qa-audit-pipeline-design.md
   - Remove plan-orchestrator.py keyword inference refs
   - Update agent dispatch for langgraph

2. 2026-02-16-12-spec-verifier-ux-reviewer-agents-design.md
   - Remove plan-orchestrator.py keyword inference refs
   - Update agent dispatch for langgraph

3. 2026-02-16-13-slack-agent-communication-design.md
   - Remove plan-orchestrator.py SlackNotifier refs
   - Update for langgraph slack/ module

4. 2026-02-16-14-slack-app-migration-design.md
   - Remove plan-orchestrator.py refs
   - Verify Socket Mode state in langgraph slack/ module

5. 2026-02-16-15-slack-inbound-message-polling-design.md
   - Remove plan-orchestrator.py refs
   - Update poll_messages design for langgraph

6. 2026-02-18-9-ux-designer-opus-sonnet-loop-design.md
   - Remove plan-orchestrator.py refs
   - Verify suspension state in langgraph pipeline

7. 2026-02-18-16-least-privilege-agent-sandboxing-design.md
   - Remove plan-orchestrator.py refs
   - Verify AGENT_PERMISSION_PROFILES in langgraph

8. 2026-02-26-03-extract-slack-modules-design.md
   - Remove migration steps referencing plan-orchestrator.py line numbers (3623-5655, 1559, etc.)
   - Module architecture section is current and accurate (keep as-is)

9. 2026-02-26-04-pipeline-graph-nodes-design.md
   - Update execute_plan.py description from "Subprocess bridge to plan-orchestrator.py" to "Invokes executor subgraph in-process"
   - Remove subprocess bridge references

10. 2026-02-26-20-unified-langgraph-runner-design.md
    - Remove plan-orchestrator.py from "Unchanged Files" section (script is deleted)

## Design Decisions

- Split into two batches of 5 docs each, so each task is completable in one session
- The coder agent reads the audit report directly for correction details
- Documents should reflect steady-state architecture (no "was changed from" language)
- References to plan-orchestrator.py should be replaced with current langgraph_pipeline equivalents, not simply deleted (unless the entire section is obsolete)

## Acceptance Criteria

- All 10 docs corrected per audit recommendations
- Updated docs reference langgraph_pipeline/ modules instead of plan-orchestrator.py
