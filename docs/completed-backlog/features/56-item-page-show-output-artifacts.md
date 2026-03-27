# Item page: show list of output artifacts created by the item

## Summary

When an item creates output files (reports, documents, etc.), there is
no way to find them from the item page. The user has to know to look in
docs/reports/ or grep git history. The item page should show a list of
all files created or modified by the item's execution.

## What to show

- Files committed by the item's workers (from git log --grep=<slug>)
- Reports in docs/reports/ that reference the slug
- Worker output files in docs/reports/worker-output/<slug>/
- Design doc in docs/plans/

Each artifact should be a clickable link (or at least a file path) so
the user can find and review the output.

## Acceptance Criteria

- Does the item page show a list of output artifacts?
  YES = pass, NO = fail
- Does the list include files committed by the item (from git)?
  YES = pass, NO = fail
- Can the user find docs/reports/design-doc-audit.md from the
  01-audit-design-docs-for-validity item page?
  YES = pass, NO = fail




## 5 Whys Analysis

**Title:** Item page should show output artifacts

**Clarity:** 4/5
(Clear problem statement and acceptance criteria, though the underlying motivation for why this view is important could be more explicit)

**5 Whys:**

1. Why can't users currently see what outputs an item created?
   - Answer: The item page shows status and metadata but lacks integration to display or aggregate the artifacts/files the item produced

2. Why would users want to see outputs on the item page instead of finding them manually?
   - Answer: Manual discovery requires knowing where to look across multiple locations (git, docs/reports/, worker-output/, design docs) and is time-consuming and error-prone

3. Why is easy access to outputs important?
   - Answer: Users need to understand what the item actually delivered and verify it matches the intended outcomes/acceptance criteria

4. Why is verifying item delivery important?
   - Answer: Without seeing the outputs, the user can't confidently determine if the item is truly complete, meets quality standards, or needs revision

5. Why does item completion confidence matter to the system?
   - Answer: The orchestrator pipeline depends on reliable confirmation of what each item delivered to sequence dependent work and maintain overall pipeline integrity

**Root Need:** The pipeline needs verifiable output visibility so users can confirm item completion and the orchestrator can reliably track what was delivered to coordinate downstream work.

**Summary:** Item page output artifacts enable users to verify completion and provide the orchestrator with traceability needed for reliable work sequencing.
