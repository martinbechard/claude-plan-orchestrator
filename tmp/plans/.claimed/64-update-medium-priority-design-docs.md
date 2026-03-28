# Update 10 medium-priority design docs per audit recommendations

## Summary

The audit identified 10 docs with stale architecture references. Update
each per the specific corrections listed in docs/reports/design-doc-audit.md
under "Recommended Next Steps: UPDATE Documents — Medium Priority".

## Acceptance Criteria

- Are all 10 medium-priority UPDATE docs corrected per the audit?
  YES = pass, NO = fail
- Do the updated docs reference langgraph_pipeline/ modules instead of
  plan-orchestrator.py? YES = pass, NO = fail

## LangSmith Trace: ac32df6e-2b06-45ba-95ad-ae00af18fb03


## 5 Whys Analysis

Title: Synchronize design documentation with langgraph_pipeline architecture refactoring
Clarity: 4

5 Whys:

1. Why do these 10 design docs need updating?
   Because they reference the outdated plan-orchestrator.py architecture instead of the current langgraph_pipeline structure, creating a mismatch between documentation and implementation.

2. Why does the documentation reference outdated architecture?
   Because when the codebase was refactored to langgraph_pipeline, the design documents weren't systematically updated to reflect those changes.

3. Why weren't the design docs updated as part of the architectural refactoring?
   Because documentation synchronization wasn't treated as a gating requirement for the refactoring—the priority was getting the new code working, not ensuring docs stayed current.

4. Why isn't documentation maintenance part of the code change process?
   Because there's no established practice that treats design docs as a first-class artifact that must be kept in sync with implementation changes.

5. Why is this fundamentally important to fix?
   Because design documents serve as the primary way developers understand system architecture. When they diverge from the actual code, they become misleading and undermine trust, leading to confusion, poor architectural decisions, and rework.

Root Need: Establish design documentation as a synchronized, authoritative source of truth that accurately reflects the current system architecture—treating doc updates as integral to architectural changes, not optional cleanup work.

Summary: The real issue is documentation drift caused by lack of process discipline, not the existence of stale docs themselves.
