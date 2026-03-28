# Design: Remove Tilde Prefix from Cost Displays (Third Attempt)

## Overview

Three Jinja2 templates display cost values with a "~$" prefix that looks like a bug to users. This is a pure text substitution — replace every "~$" with "$" across all three files.

## Files to Modify

| File | Occurrences |
|------|-------------|
| langgraph_pipeline/web/templates/analysis.html | 16 |
| langgraph_pipeline/web/templates/item.html | 2 |
| langgraph_pipeline/web/templates/completions.html | 2 |

**Total: 20 occurrences**

## Acceptance Check

After the change, `grep '~\$' langgraph_pipeline/web/` must return zero matches.

## Design Decision

No logic change is needed. The tilde was a display convention that has been deprecated per MEMORY.md. Replacing every literal "~$" with "$" is sufficient.
