# Design: Read-Only Analysis Task Workflow

## Reference
- Backlog item: docs/feature-backlog/17-read-only-analysis-task-workflow.md
- Depends on: 16-least-privilege-agent-sandboxing (permission profiles)
- Prior design: docs/plans/2026-02-18-17-read-only-analysis-task-workflow-design.md
- Date: 2026-02-19

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

## Key Design Decisions

### 1. No plan YAML for analysis items

Analysis tasks are single-pass: one Claude session with a read-only agent produces
a report. There is no multi-phase plan, no orchestrator invocation, and no
verification loop.

### 2. Agent selection based on analysis type

The analysis backlog item specifies an "Analysis Type" field. The pipeline maps
this to one of the read-only agents from the permission profile system (feature 16):

| Analysis Type       | Agent          |
|---------------------|----------------|
| code-review         | code-reviewer  |
| codebase-analysis   | code-explorer  |
| test-coverage       | qa-auditor     |
| test-results        | e2e-analyzer   |
| spec-compliance     | spec-verifier  |
| (default)           | code-reviewer  |

All agents map to the READ_ONLY permission profile.

### 3. Report delivery

Analysis results are delivered in up to two ways:
1. A Slack message summary posted to the orchestrator-reports channel
2. A full markdown report saved to docs/reports/<slug>.md

The backlog item "Output Format" field controls this: "slack", "markdown", or
"both" (default: "both").

### 4. New Slack channel: orchestrator-reports

Added "reports" to SLACK_CHANNEL_ROLE_SUFFIXES in plan-orchestrator.py with
get_type_channel_id mapping item_type="analysis" to the "reports" suffix.

### 5. Completed analysis archive

Analysis items archive to docs/completed-backlog/analyses/ (parallel to
defects/ and features/). Added to COMPLETED_DIRS mapping.

### 6. Filesystem watching

ANALYSIS_DIR added to the watch list and scan_all_backlogs() returns analysis
items after defects and features.

## Files Modified

### scripts/auto-pipeline.py
- Constants: ANALYSIS_DIR, COMPLETED_ANALYSES_DIR, REPORTS_DIR
- ANALYSIS_DIR and related dirs added to REQUIRED_DIRS
- "analysis" added to COMPLETED_DIRS mapping
- ANALYSIS_TYPE_TO_AGENT mapping and DEFAULT_ANALYSIS_AGENT constant
- ANALYSIS_PROMPT_TEMPLATE for the analyzer session prompt
- parse_analysis_metadata() to extract type, scope, and output format
- process_analysis_item() and _process_analysis_inner() for the lightweight workflow
- _deliver_analysis_report() for Slack/markdown report delivery
- scan_all_backlogs() includes analysis items
- main_loop() filesystem watcher watches ANALYSIS_DIR
- process_item() branches on item_type == "analysis"

### scripts/plan-orchestrator.py
- "reports" added to SLACK_CHANNEL_ROLE_SUFFIXES
- get_type_channel_id() suffix_map includes "analysis" -> "reports"

### tests/test_auto_pipeline.py
- Tests for constants (ANALYSIS_DIR, COMPLETED_ANALYSES_DIR, REPORTS_DIR, COMPLETED_DIRS)
- Tests for ANALYSIS_TYPE_TO_AGENT mapping
- Tests for parse_analysis_metadata() (full, defaults, missing file)
- Tests for scan_all_backlogs() including analysis items

### tests/test_plan_orchestrator.py
- Test that SLACK_CHANNEL_ROLE_SUFFIXES includes "reports"
- Test that get_type_channel_id("analysis") returns reports channel
- Test for unknown type returns empty string

## Acceptance Criteria Mapping

1. Analysis backlog directory is scanned by the pipeline
   -> scan_all_backlogs() includes scan_directory(ANALYSIS_DIR, "analysis")
2. Analysis tasks run with read-only agent permissions
   -> Agent selected from ANALYSIS_TYPE_TO_AGENT, all READ_ONLY profile
3. Reports are delivered via Slack and/or saved to docs/reports/
   -> process_analysis_item() handles both delivery paths
4. No project files are modified during analysis task execution
   -> READ_ONLY permission profile from feature 16 enforces this
5. Pipeline correctly distinguishes analysis items from feature/defect items
   -> item_type == "analysis" branch in process_item()
