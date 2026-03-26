# Timeline: all child runs classified as "Other" — tools and LLM calls not detected

## Status: Open

## Priority: Medium

## Summary

The Gantt timeline shows every bar in the grey "Other" colour regardless of
whether the run is a Claude Code tool call or an LLM invocation. Tool calls
(Read, Write, Bash, etc.) and LLM calls (assistant_text, LangGraph) should
each get their own distinct colour.

## Root Cause

The bar_color() and text_color() macros in proxy_trace.html match against
substrings like "llm", "chat", "claude", "tool", "function". None of the
actual names stored in the traces DB match these keywords:

Tool calls stored as: Bash, Edit, Glob, Grep, Read, Write, Skill
LLM calls stored as:  assistant_text, LangGraph (child runs)
Graph nodes stored as: scan_backlog, intake_analyze, execute_plan, etc.

All fall through to the "Other" branch because none contain the expected
keywords.

## Fix

Replace the substring-keyword approach with explicit name matching:

Tool category — exact match against known Claude Code tool names:
  Bash, Edit, Write, Read, Glob, Grep, Skill, MultiEdit, NotebookEdit

LLM/Claude category — match names that represent model invocations:
  assistant_text, LangGraph (when appearing as a child), any name
  containing "claude", "llm", "model", or "ChatAnthropic"

Graph nodes (Other) — everything else: scan_backlog, execute_plan, etc.

Also verify in the LangSmith trace how Claude Code worker invocations are
logged — confirm whether they appear as a single child run named "LangGraph"
or "ChatAnthropic" or something else, and classify accordingly.
