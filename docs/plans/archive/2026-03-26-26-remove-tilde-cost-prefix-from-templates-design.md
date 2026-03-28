# Remove Tilde Cost Prefix from Templates

## Overview

Three Jinja2 template files contain 19 occurrences of the "~$" cost display
pattern. These must be replaced with plain "$" to match the established
convention documented in MEMORY.md and already applied to dashboard.js.

## Key Files to Modify

- langgraph_pipeline/web/templates/item.html — 2 occurrences
- langgraph_pipeline/web/templates/completions.html — 2 occurrences
- langgraph_pipeline/web/templates/analysis.html — 15 occurrences

## Design Decision

A simple string replacement of "~$" with "$" across all three files is the
correct fix. No logic changes, no new helpers, no JS side changes (already
clean). The JS fmtCost function is unaffected.
