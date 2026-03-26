# Remove tilde prefix from all cost displays in templates (third attempt)

## Status: Open

## Priority: High

## THIRD ATTEMPT — Previous two implementations did not actually remove the tildes

Item 12 and item 26 were both marked "completed" without removing the tildes.
The templates still contain 20 occurrences of the tilde prefix.

## Problem

Cost values in Jinja2 templates display as "~$0.0123" instead of "$0.0123".
The tilde looks like a bug to users.

## What Must Be Changed

Replace every "~$" with "$" in these files:
- langgraph_pipeline/web/templates/analysis.html (16 occurrences)
- langgraph_pipeline/web/templates/item.html (2 occurrences)
- langgraph_pipeline/web/templates/completions.html (2 occurrences)

This includes both display values (e.g. "~$0.0123") and table header text
(e.g. "Exclusive ~$" should become "Exclusive $").

Do NOT add tildes back anywhere. The MEMORY.md convention explicitly says
to use plain "$" without tilde.

## Acceptance Criteria

- Does grep '~\$' across all three template files return zero matches?
  YES = pass, NO = fail
- Does the /analysis page show "$55.61" (no tilde) for cost values?
  YES = pass, NO = fail (WARN if cannot verify at validation time)
- Does the /completions page show "$0.0123" (no tilde) for cost values?
  YES = pass, NO = fail (WARN if cannot verify at validation time)
- Does the /item/<slug> page show "$1.23" (no tilde) for cost values?
  YES = pass, NO = fail (WARN if cannot verify at validation time)
- Does grep '~\$' across ALL files in langgraph_pipeline/web/ return
  zero matches? YES = pass, NO = fail

## LangSmith Trace: e3fea1f5-4f41-4c7e-a866-78301de9d9bf
