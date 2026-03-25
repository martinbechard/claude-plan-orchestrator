# Execution Cost Log Analysis

## Status: Open

## Priority: Medium

## Summary

Aggregate the structured execution cost logs under `docs/reports/execution-costs/`
to identify token and time waste patterns across pipeline items and agent types. Post
a ranked Slack report with concrete restructuring recommendations.

## Analysis Instructions

1. Read all JSON files under `docs/reports/execution-costs/`. Each file covers one
   pipeline item and contains a list of task records, each with `task_id`,
   `agent_type`, `model`, `input_tokens`, `output_tokens`, `cost_usd`, `duration_s`,
   and `tool_calls` (each call has `tool`, optional `file_path`, optional `command`,
   optional `result_bytes`).

2. Aggregate read volume by file path: for every `Read` tool call across all task
   records, sum `result_bytes` grouped by `file_path`. Rank the top 10 file paths
   by total bytes read.

3. Rank agent types by total token cost: sum `input_tokens + output_tokens` grouped
   by `agent_type` across all items and tasks. Rank agent types from highest to
   lowest.

4. Identify intra-item repeated reads: for each item, find any `file_path` that
   appears in `Read` tool calls across two or more distinct tasks within that same
   item. List the item slug, file path, and the task ids that each performed the
   redundant read.

5. Post a structured Slack report to `orchestrator-notifications` with the following
   sections:

   - *Top files by total read volume* — ranked table of file path and cumulative
     bytes read
   - *Agent types by token cost* — ranked table of agent type and total tokens
   - *Intra-item repeated reads* — for each flagged item, list the file and the
     task ids that redundantly loaded it
   - *Recommendations* — concrete restructuring actions, for example: "tasks X and
     Y in item Z both load files A, B, C — consider merging into one invocation"
     or "file F is loaded in every item — consider pre-loading it in the system
     prompt"

## Scope

- Input: all files matching `docs/reports/execution-costs/*.json`
- Output: Slack report posted to `orchestrator-notifications`
- No files modified or created beyond the Slack message

## Source

Created on 2026-03-24 as part of feature 12 (structured execution cost log and
automated analysis).
