# Design: Timeline — All Items Show as Other (Review Pass)

## Overview

This defect was previously implemented and is returning for validation. The
bar_color() and text_color() Jinja2 macros in proxy_trace.html were updated to
use exact tool-name matching and substring fallback for LLM names. The legend
matches the three categories (LLM, Tool, Other) with correct colors.

## Current State

The macros at lines 151-164 and 167-180 of proxy_trace.html already implement:

1. Exact set membership for Claude Code tool names (Bash, Edit, Write, Read,
   Glob, Grep, Skill, MultiEdit, NotebookEdit)
2. Substring fallback on lower-cased name for LLM indicators (claude, llm,
   model, chatanthropic, langgraph, assistant)
3. Amber fallback for graph nodes / other

The legend at lines 329-336 shows LLM (#7c3aed), Tool (#0891b2), Other (#f59e0b).

## Scope

Single task: validate the existing implementation against the acceptance criteria
in the work item. If any criterion fails, fix it in place.

## Files

- langgraph_pipeline/web/templates/proxy_trace.html (validate / fix if needed)
