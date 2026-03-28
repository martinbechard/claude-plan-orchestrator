# Design: Read-Only Analysis Task Workflow

## Reference
- Backlog item: docs/feature-backlog/17-read-only-analysis-task-workflow.md
- Depends on: 16-least-privilege-agent-sandboxing (completed)
- Prior designs: docs/plans/2026-02-18-17-read-only-analysis-task-workflow-design.md,
  docs/plans/2026-02-19-17-read-only-analysis-task-workflow-design.md
- Date: 2026-02-26

## Architecture Overview

A third backlog type ("analysis") sits alongside "defect" and "feature". Analysis
items live in docs/analysis-backlog/, use read-only agents, skip the plan/verify
cycle entirely, and deliver structured reports via Slack and/or markdown files.

```
  Existing pipeline flow (feature/defect):
  +----------+   +----------+   +----------+   +----------+
  | Scan     |-->| Plan     |-->| Execute  |-->| Verify   |--> Archive
  | backlog  |   | creation |   | (orch)   |   | symptoms |
  +----------+   +----------+   +----------+   +----------+

  New analysis flow:
  +----------+   +--------------+   +----------+
  | Scan     |-->| Run analyzer |-->| Deliver  |--> Archive
  | backlog  |   | (read-only)  |   | report   |
  +----------+   +--------------+   +----------+
```

## Implementation Status

The core feature is already implemented across two prior iterations. This plan
captures the remaining work: adding test coverage for the execution and delivery
paths (process_analysis_item, _process_analysis_inner, _deliver_analysis_report)
which currently lack dedicated unit tests.

## Key Design Decisions

### 1. No plan YAML for analysis items
Analysis tasks are single-pass: one Claude session with a read-only agent produces
a report. No multi-phase plan, no orchestrator invocation, no verification loop.

### 2. Agent selection based on analysis type
The analysis backlog item specifies an "Analysis Type" field mapped to read-only agents:

| Analysis Type       | Agent          |
|---------------------|----------------|
| code-review         | code-reviewer  |
| codebase-analysis   | code-explorer  |
| test-coverage       | qa-auditor     |
| test-results        | e2e-analyzer   |
| spec-compliance     | spec-verifier  |
| (default)           | code-reviewer  |

All agents use the READ_ONLY permission profile from feature 16.

### 3. Report delivery
Results delivered via:
1. Slack message summary to orchestrator-reports channel
2. Full markdown report saved to docs/reports/<slug>.md

Controlled by "Output Format" field: "slack", "markdown", or "both" (default).

### 4. Slack channel: orchestrator-reports
"reports" added to SLACK_CHANNEL_ROLE_SUFFIXES, with get_type_channel_id mapping
item_type="analysis" to the "reports" suffix.

### 5. Archive destination
Analysis items archive to docs/completed-backlog/analyses/.

## Files Already Modified
- scripts/auto-pipeline.py: Constants, type mapping, parse_analysis_metadata(),
  process_analysis_item(), _process_analysis_inner(), _deliver_analysis_report(),
  scan_all_backlogs(), main_loop() watch, process_item() branch
- scripts/plan-orchestrator.py: "reports" in SLACK_CHANNEL_ROLE_SUFFIXES,
  get_type_channel_id() analysis mapping

## Files to Modify (Remaining)
- tests/test_auto_pipeline.py: Add tests for process_analysis_item(),
  _process_analysis_inner(), and _deliver_analysis_report()
- tests/test_plan_orchestrator.py: Verify existing Slack channel tests are sufficient

## Acceptance Criteria Mapping
1. Analysis backlog directory is scanned -> scan_all_backlogs() includes ANALYSIS_DIR
2. Read-only agent permissions -> READ_ONLY profile via build_permission_flags
3. Reports delivered via Slack/markdown -> _deliver_analysis_report()
4. No project files modified -> READ_ONLY permission profile enforces
5. Pipeline distinguishes analysis items -> item_type == "analysis" branch
