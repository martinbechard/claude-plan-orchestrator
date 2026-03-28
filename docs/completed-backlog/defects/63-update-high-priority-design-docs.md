# Update 7 high-priority design docs per audit recommendations

## Summary

The audit identified 7 docs that actively mislead agents with references
to the deleted plan-orchestrator.py. Update each per the specific
corrections listed in docs/reports/design-doc-audit.md under
"Recommended Next Steps: UPDATE Documents — High Priority".

## Acceptance Criteria

- Are all 7 high-priority UPDATE docs corrected per the audit?
  YES = pass, NO = fail
- Do the updated docs reference langgraph_pipeline/ paths instead of
  plan-orchestrator.py? YES = pass, NO = fail




## 5 Whys Analysis

Title: Update stale design docs that reference deleted code
Clarity: 4

5 Whys:

1. **Why do these design docs need updating?** Because they contain references to plan-orchestrator.py, a file that no longer exists, actively misleading anyone reading the documentation.

2. **Why is referencing deleted code a high-priority problem?** Because agents and developers relying on these docs will attempt to find or implement patterns from non-existent code paths, causing confusion and potential architectural misalignment.

3. **Why were these 7 docs flagged as "high-priority" instead of medium?** Because these are frequently-referenced architectural docs that many other docs and implementations depend on—incorrect information at this layer cascades broadly.

4. **Why did documentation become stale when the code changed?** Because the refactoring from plan-orchestrator.py to langgraph_pipeline/ wasn't accompanied by a synchronized documentation update, creating a timing gap.

5. **Why does this timing gap exist?** Because documentation updates aren't enforced as part of the code refactoring workflow—there's no checkpoint ensuring that architectural changes trigger documentation reviews.

Root Need: Documentation must be kept in sync with code architecture changes to maintain agent/developer trust in the design documentation as a source of truth.

Summary: High-priority design docs are misleading agents because they reference deleted code, indicating a need for synchronized documentation-code refactoring workflows.
