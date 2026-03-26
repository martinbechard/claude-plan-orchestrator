# Design: Tool Call Attribution Table Missing Attribution Column (Item 38)

## Overview

The Tool Call Cost Attribution table in `analysis.html` has an "Est. ~$" column
header and cell values prefixed with "~$". The tilde prefix violates the project
convention (costs display as plain "$0.0123") and the acceptance criteria require
the header to say "Est. Cost" or similar.

The attribution logic itself (proportional split by result_bytes in
`proxy.get_tool_call_attribution()`) is correct and already implemented.

## Files to Modify

- `langgraph_pipeline/web/templates/analysis.html` — fix column header and cell values
- `plugin.json` — patch version bump
- `RELEASE-NOTES.md` — changelog entry

## Design Decisions

### Column header

Change `Est. ~$` → `Est. Cost` to satisfy acceptance criterion 3 and match the
plain-dollar convention used elsewhere in the UI.

### Cell values

Change `~${{ "%.6f" | format(ta.estimated_cost_usd) }}` →
`${{ "%.6f" | format(ta.estimated_cost_usd) }}` to remove the tilde prefix.

## No Structural Changes

The table columns, data pipeline, and SQL query are correct. Only the display
strings in the template change.
