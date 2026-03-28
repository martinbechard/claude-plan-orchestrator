# Update 3 low-priority design docs per audit recommendations

## Summary

The audit identified 3 docs needing clarification that plan-orchestrator.py
references are historical context, not instructions. Update each per the
corrections listed in docs/reports/design-doc-audit.md under
"Recommended Next Steps: UPDATE Documents — Low Priority".

## Acceptance Criteria

- Are all 3 low-priority UPDATE docs corrected per the audit?
  YES = pass, NO = fail
- Is it clear in each doc that plan-orchestrator.py references are
  historical and not actionable? YES = pass, NO = fail

## LangSmith Trace: 63a7eaf7-36b1-4db3-872c-2e57e66d12f3


## 5 Whys Analysis

**Title:** Clarify historical vs. current design context to prevent misguided implementation decisions

**Clarity:** 4
(Specific about scope and references the audit report, but requires familiarity with the audit findings)

**5 Whys:**

1. **Why do these 3 design docs need updating?**
   Because the audit discovered that references to plan-orchestrator.py in these docs read like current system instructions when they're actually historical context about how the system evolved.

2. **Why is this distinction between historical and current design important?**
   Because developers reading these docs interpret them as authoritative descriptions of how the system *should* work, not how it *used to* work, leading them to make decisions based on outdated design assumptions.

3. **Why would developers making decisions based on outdated design context cause problems?**
   Because they would modify code, add features, or maintain systems based on superseded architectural decisions, creating inconsistencies with the actual current design and introducing bugs or technical debt.

4. **Why wasn't this distinction clear when these docs were written or when plan-orchestrator.py changed?**
   Because as systems evolve incrementally, historical design context naturally gets embedded in documentation without explicit markers separating "why we made past decisions" from "how the system works now."

5. **Why does this blurring persist across iterative development cycles?**
   Because there's no systematic practice of marking or reviewing docs when code changes to maintain the boundary between historical narrative and current steady-state reference material.

**Root Need:** Establish a documentation maintenance practice that explicitly separates historical design context from current system requirements, ensuring design docs remain reliable references that don't mislead maintainers with outdated assumptions.

**Summary:** Design documentation must clearly flag historical references to prevent developers from making implementation decisions based on superseded design context.
