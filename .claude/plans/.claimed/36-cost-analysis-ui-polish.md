# Cost analysis page: remove wasted space and fix amateurish pagination UI

## Status: Open

## Priority: Medium

## Summary

Two UI issues on the /analysis page:

### 1. Disclaimer text wastes space
The two lines at the top ("API-Equivalent Estimates - subscription charges
may differ" and "Cost is recorded at the agent task level only. Tool calls
carry no direct cost.") take up vertical space on every page load. Replace
with an info icon/button that shows this text in a popup/tooltip on click.

### 2. Pagination styling is amateurish
The table pagination has no left padding, the page count text is hard to
read, and the overall appearance is unprofessional. The pagination controls
need proper spacing, readable font size, and visual alignment with the
table.

## Acceptance Criteria

- Are the two disclaimer lines replaced with a single info icon that shows
  the text on click/hover? YES = pass, NO = fail
- Does the pagination have left padding aligned with the table?
  YES = pass, NO = fail
- Is the page count text clearly readable (adequate font size, contrast)?
  YES = pass, NO = fail
- Use the frontend-design skill when implementing this item.

## LangSmith Trace: 68e8a59a-279a-470a-ac7a-31b576cafe7b
