# Remove tilde prefix from all cost displays in templates

## Status: Open

## Priority: Medium

## Summary

Cost values in Jinja2 templates still use the tilde prefix (e.g. showing
"~$0.0123" instead of "$0.0123"). This was supposed to be fixed by defect 12
but the pipeline only partially completed it. The MEMORY.md convention has
been corrected to say "do NOT use tilde" but 19 occurrences remain in the
template files.

## Locations (confirmed by grep)

item.html: 2 occurrences (total cost header, completion history cost column)
completions.html: 2 occurrences (summary stat, table row cells)
analysis.html: 15 occurrences (summary cards, table headers with "~$" in
  column names, table cells for exclusive/inclusive/total/avg/estimated costs)

## Fix

Replace every instance of the pattern in these three template files:
- Replace "~$" with "$" in display values
- Replace "~$" with "$" in table header text (e.g. "Exclusive ~$" becomes
  "Exclusive $")

The JS side (dashboard.js fmtCost) is already clean — no tilde there.

Do NOT add tildes back anywhere. The MEMORY.md convention now explicitly
says to use plain "$" without tilde.
