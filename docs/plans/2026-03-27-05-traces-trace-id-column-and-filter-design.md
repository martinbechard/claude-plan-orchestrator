# Design: Traces trace_id column and filter

## Overview

This is a validation/fix task for previously-implemented functionality. The traces
list page should display a trace_id column (truncated, copyable, monospace) and
provide a filter input to narrow results by trace_id or prefix.

## Current State

Based on codebase exploration, the feature appears to already be implemented:

- proxy_list.html has a Trace ID column showing first 8 chars with copy button
- GET /proxy endpoint accepts a trace_id query parameter
- TracingProxy.list_runs() and count_runs() support trace_id filtering
- The filter form includes a trace_id text input

## Key Files

- langgraph_pipeline/web/templates/proxy_list.html - traces list template
- langgraph_pipeline/web/routes/proxy.py - GET /proxy endpoint handler
- langgraph_pipeline/web/proxy.py - TracingProxy.list_runs() and count_runs()

## Task

Validate all acceptance criteria from the work item. If any criterion fails,
fix it in place. The validator agent will verify after implementation.

## Acceptance Criteria (from work item)

1. Truncated/copyable trace_id column in traces table
2. Filter input accepts trace_id (or prefix) to narrow the list
3. Optional: visual grouping of runs sharing the same thread_id

## Design Decisions

- Since the feature was previously implemented, the task is validation-first
- Do not rewrite from scratch; check what exists and fix gaps
- The coder agent will read the work item directly for full requirements
