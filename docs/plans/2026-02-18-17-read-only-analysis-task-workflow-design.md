# Design: Read-Only Analysis Task Workflow

## Reference
- Backlog item: docs/feature-backlog/17-read-only-analysis-task-workflow.md
- Depends on: 16-least-privilege-agent-sandboxing (permission profiles)
- Date: 2026-02-18

## Architecture Overview

Add a third backlog type ("analysis") alongside "defect" and "feature". Analysis
items live in docs/analysis-backlog/, use read-only agents, skip the plan/verify
cycle entirely, and deliver structured reports via Slack and/or markdown files.

```
  Existing pipeline flow (feature/defect):
  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
  │ Scan     │──>│ Plan     │──>│ Execute  │──>│ Verify   │──> Archive
  │ backlog  │   │ creation │   │ (orch)   │   │ symptoms │
  └──────────┘   └──────────┘   └──────────┘   └──────────┘

  New analysis flow:
  ┌──────────┐   ┌──────────────┐   ┌──────────┐
  │ Scan     │──>│ Run analyzer │──>│ Deliver  │──> Archive
  │ backlog  │   │ (read-only)  │   │ report   │
  └──────────┘   └──────────────┘   └──────────┘
```

## Key Design Decisions

### 1. No plan YAML for analysis items

Analysis tasks are single-pass: one Claude session with a read-only agent produces
a report. There is no multi-phase plan, no orchestrator invocation, and no
verification loop. This keeps the workflow lightweight and fast.

### 2. Agent selection based on analysis type

The analysis backlog item specifies an "Analysis Type" field. The pipeline maps
this to one of the read-only agents already defined in the permission profile
system (feature 16):

| Analysis Type       | Agent          |
|---------------------|----------------|
| code-review         | code-reviewer  |
| codebase-analysis   | code-explorer  |
| test-coverage       | qa-auditor     |
| test-results        | e2e-analyzer   |
| spec-compliance     | spec-verifier  |
| (default)           | code-reviewer  |

All of these agents map to the READ_ONLY permission profile, so no code
modifications are possible.

### 3. Report delivery

Analysis results are delivered in up to two ways:
1. A Slack message summary posted to the new orchestrator-reports channel
2. A full markdown report saved to docs/reports/<slug>.md

The backlog item's "Output Format" field controls this: "slack", "markdown", or
"both" (default: "both").

### 4. New Slack channel: orchestrator-reports

Add "reports" to SLACK_CHANNEL_ROLE_SUFFIXES in plan-orchestrator.py. This follows
the existing pattern (features, defects, questions, notifications). The
get_type_channel_id method in SlackNotifier needs a small update to map
item_type="analysis" to the "reports" suffix.

### 5. Completed analysis archive

Analysis items archive to docs/completed-backlog/analyses/ (parallel to
defects/ and features/). Add to COMPLETED_DIRS mapping.

### 6. Filesystem watching

The BacklogWatcher and main_loop already iterate over watch directories. Add
ANALYSIS_DIR to the watch list and scan_all_backlogs().

## Analysis Backlog Item Format

```markdown
# Analysis Title

## Status: Open

## Priority: Medium

## Analysis Type: code-review

## Scope
- src/components/
- src/utils/

## Output Format: both

## Instructions
Detailed instructions for what to analyze and what to look for.
```

## Files to Create/Modify

### New files
- docs/analysis-backlog/ (directory) - created by ensure_directories()
- docs/completed-backlog/analyses/ (directory)
- docs/reports/ (directory)

### Modified files
- scripts/auto-pipeline.py:
  - Add ANALYSIS_DIR, COMPLETED_ANALYSES_DIR, REPORTS_DIR constants
  - Add ANALYSIS_DIR and related dirs to REQUIRED_DIRS
  - Add "analysis" to COMPLETED_DIRS mapping
  - Add ANALYSIS_PROMPT_TEMPLATE for the analyzer session prompt
  - Add process_analysis_item() function (single-pass: run agent, deliver report)
  - Add parse_analysis_metadata() to extract type, scope, and output format
  - Update scan_all_backlogs() to include analysis items
  - Update main_loop() filesystem watcher to watch ANALYSIS_DIR
  - Update _process_item_inner() to branch on item_type == "analysis"

- scripts/plan-orchestrator.py:
  - Add "reports" to SLACK_CHANNEL_ROLE_SUFFIXES
  - Update get_type_channel_id() suffix_map to include "analysis" -> "reports"

- tests/test_auto_pipeline.py:
  - Tests for parse_analysis_metadata()
  - Tests for process_analysis_item() (mocked Claude subprocess)
  - Tests for scan_all_backlogs() including analysis items

- tests/test_plan_orchestrator.py:
  - Test that SLACK_CHANNEL_ROLE_SUFFIXES includes "reports"
  - Test that get_type_channel_id("analysis") returns the reports channel

## Acceptance Criteria Mapping

1. Analysis backlog directory is scanned by the pipeline
   -> scan_all_backlogs() includes scan_directory(ANALYSIS_DIR, "analysis")
2. Analysis tasks run with read-only agent permissions
   -> Agent selected from ANALYSIS_TYPE_TO_AGENT mapping, all READ_ONLY profile
3. Reports are delivered via Slack and/or saved to docs/reports/
   -> process_analysis_item() handles both delivery paths
4. No project files are modified during analysis task execution
   -> READ_ONLY permission profile from feature 16 enforces this
5. Pipeline correctly distinguishes analysis items from feature/defect items
   -> item_type == "analysis" branch in _process_item_inner()
