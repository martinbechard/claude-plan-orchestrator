# Instead of completions, we should use Work item as the title in the UI and the e

## Status: Open

## Priority: Medium

## Summary

**Title:** Rename "Completions" to "Work Items" across UI and database

**Classification:** feature - This is a terminology/naming change to align the domain model's language, not a bug fix.

**5 Whys:**

1. **Why rename "Completions" to "Work Items"?** Because "Completions" only describes finished runs, but the entity represents the full lifecycle — queued, in-progress, failed, and completed — so the name is misleading.

2. **Why is the current name misleading?** Because the feature was originally built to show finished pipeline runs, and the name stuck even as it grew to encompass all work item states and details.

3. **Why does a misleading name matter to users?** Because users see "Completions" in the nav menu and expect only finished items, creating confusion when they find active and failed items there too, and when detail pages already call things "work items."

4. **Why is there already inconsistent terminology in the codebase?** Because developers organically adopted "work item" as the more accurate term in routes, comments, and documentation, but never went back to update the original UI labels and database table name.

5. **Why wasn't this inconsistency addressed earlier?** Because there was no deliberate domain-language alignment effort — the mismatch accumulated as incremental features were added without revisiting the foundational naming.

**Root Need:** Establish "Work Item" as the single ubiquitous domain term across UI, database, and code to eliminate the legacy "completions" label that no longer reflects the entity's full-lifecycle scope.

**Description:**
Rename "Completions" to "Work Items" throughout the system: the nav menu link in base.html, the page title/heading in completions.html, the `/completions` route path, and the `completions` database table. This aligns the UI and persistence layer with the "work item" terminology already used in route modules, comments, and documentation, creating consistent domain language across the entire application.

## Source

Created from Slack message by U0AEWQYSLF9 at 1775164944.826789.

## LangSmith Trace: e19267d7-2b1b-4cf1-a0e5-912ec254505d
