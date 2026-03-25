# Design: Execution Cost Log Analysis

- **Work item:** .claude/plans/.claimed/cost-analysis.md
- **Created:** 2026-03-24

## Architecture Overview

This is a single-pass analysis task. A coder agent reads all JSON files under
`docs/reports/execution-costs/`, computes three aggregations in memory, and posts
a ranked Slack report to `orchestrator-notifications`. No files are created or
modified beyond the Slack message.

The agent uses the existing `SlackNotifier` class in `scripts/plan-orchestrator.py`
(imported via `sys.path`) and the SLACK_BOT_TOKEN / channel IDs available in the
environment, consistent with how the orchestrator itself posts notifications.

## Key Files

| File | Role |
|------|------|
| `docs/reports/execution-costs/*.json` | Input data — one file per pipeline item |
| `scripts/plan-orchestrator.py` | Source of `SlackNotifier` for Slack posting |

No files are created or modified as part of this task.

## Aggregation Logic

1. **Top files by read volume** — for every `Read` tool call across all task records,
   sum `result_bytes` grouped by `file_path`. Rank the top 10 by total bytes.

2. **Agent types by token cost** — sum `input_tokens + output_tokens` grouped by
   `agent_type`. Rank from highest to lowest.

3. **Intra-item repeated reads** — for each item (JSON file), find any `file_path`
   that appears in `Read` tool calls across two or more distinct tasks. Report the
   item slug, file path, and task ids.

4. **Recommendations** — derive concrete restructuring suggestions from the above
   (e.g. merge tasks with overlapping reads, pre-load hot files in system prompt).

## Report Structure

Slack message posted to `orchestrator-notifications`:

```
:bar_chart: *Execution Cost Log Analysis*

*Top files by total read volume*
...ranked table...

*Agent types by token cost*
...ranked table...

*Intra-item repeated reads*
...per-item list...

*Recommendations*
...concrete actions...
```

## Design Decisions

- **In-memory aggregation only**: the JSON files are small enough to load entirely;
  no intermediate files needed.
- **SlackNotifier reuse**: importing from plan-orchestrator.py avoids duplicating
  Slack API logic. The agent can also fall back to a direct `requests` call if the
  import path is unavailable.
- **Graceful empty-data handling**: if `docs/reports/execution-costs/` is empty or
  absent, the agent posts a short "no data yet" message rather than failing.
