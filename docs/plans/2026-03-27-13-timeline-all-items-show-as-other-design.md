# Design: Timeline all items show as "Other"

## Status: Review Required (previously implemented)

## Overview

The Gantt timeline in proxy_trace.html was showing all child run bars in grey
"Other" colour because the bar_color() and text_color() Jinja macros used
substring matching against keywords that never appeared in actual trace data.

## Prior Implementation

The fix has already been applied to
langgraph_pipeline/web/templates/proxy_trace.html (lines 148-180).

The macros were rewritten to use:

1. **Tool category** - exact match against known Claude Code tool names:
   Bash, Edit, Write, Read, Glob, Grep, Skill, MultiEdit, NotebookEdit.
   Colour: #0891b2 (teal).

2. **LLM category** - substring match (lower-cased) against: claude, llm,
   model, chatanthropic, langgraph, assistant.
   Colour: #7c3aed (purple).

3. **Other** - everything else (graph nodes like scan_backlog, execute_plan).
   Colour: #f59e0b (amber).

## Key Files

- langgraph_pipeline/web/templates/proxy_trace.html - bar_color() and
  text_color() macros (already modified)

## Design Decisions

- Exact match for tools avoids false positives (e.g. a node named "ReadConfig"
  should not match as a tool)
- Substring match for LLM is appropriate because model invocation names vary
  (assistant_text, LangGraph, ChatAnthropic) and new ones may appear
- "Other" gets a warm amber instead of grey so graph nodes are visually
  distinct rather than appearing as unclassified

## Validation Focus

Since this was previously implemented, the plan focuses on verifying that the
existing implementation correctly addresses all acceptance criteria from the
work item.
