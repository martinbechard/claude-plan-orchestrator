# Design: Timeline — All Items Show as Other

## Overview

The Gantt timeline in `proxy_trace.html` renders every child run bar in the grey
"Other" colour. The root cause is that the `bar_color()` and `text_color()` Jinja2
macros use substring keywords (`"llm"`, `"chat"`, `"claude"`, `"tool"`, `"function"`)
that do not match any of the actual run names stored in the traces DB.

## Actual Run Name Inventory

| Category | Names stored in DB |
|----------|-------------------|
| Tool calls | `Bash`, `Edit`, `Write`, `Read`, `Glob`, `Grep`, `Skill`, `MultiEdit`, `NotebookEdit` |
| LLM / Claude | `assistant_text`, `LangGraph` (child), names containing `claude`, `llm`, `model`, `ChatAnthropic` |
| Graph nodes (Other) | `scan_backlog`, `intake_analyze`, `execute_plan`, etc. |

Because none of the tool call names contain the substring `"tool"` or `"function"`,
and none of the LLM names contain `"chat"` or `"gpt"`, all runs fall through to the
amber "Other" branch.

## Fix

Replace the keyword-substring approach in both macros with a two-step strategy:

1. **Exact set membership** for the known Claude Code tool names (case-sensitive).
2. **Substring fallback** on the lower-cased name for LLM indicators: `claude`,
   `llm`, `model`, `chatanthropic`, `langgraph`, `assistant`.

The ordering matters: tool check first, LLM check second, "Other" last.

## Files to Modify

- `langgraph_pipeline/web/templates/proxy_trace.html` — update `bar_color()` and
  `text_color()` macros (lines 135–156).

No backend changes are needed; the fix is entirely in the Jinja2 template.

## Test Coverage

Existing proxy tests in `tests/` verify template rendering. The validator will
confirm build + full test suite pass after the change.
