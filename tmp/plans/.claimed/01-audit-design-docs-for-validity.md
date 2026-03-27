# Audit design docs in docs/plans/ for validity and accuracy

## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


## Status: Open

## Priority: Medium

## Summary

There are 142 design documents in docs/plans/. Many reference the old
plan-orchestrator.py (now deleted) or contain directives that are now wrong
(e.g. the tilde cost prefix convention that was explicitly removed). Pipeline
agents read these docs during plan creation and may follow outdated
instructions.

## Analysis Instructions

1. Read each design document in docs/plans/.
2. For each document, determine:
   - Does it reference scripts/plan-orchestrator.py or the old auto-pipeline
     code that no longer exists? If so, flag for update or deletion.
   - Does it contain directives or conventions that conflict with current
     CLAUDE.md, MEMORY.md, or the actual codebase? If so, flag for update.
   - Is the corresponding backlog item completed? If so, does the design doc
     still provide value as architecture reference, or is it purely
     implementation detail that is now in the code?
   - Does the document reference file paths, function names, or modules that
     no longer exist?
3. Classify each document as one of:
   - KEEP: still accurate and useful as architecture reference
   - UPDATE: useful but contains outdated references that need correction
   - ARCHIVE: completed work, no longer useful, can be moved to an archive
   - DELETE: contains harmful outdated directives that could mislead agents
4. Produce a summary report listing each document with its classification
   and the specific issues found.
5. For each document classified as UPDATE, create a separate analysis task
   to review and update that specific document.

## Output

Post a summary to Slack and save the classification report to
docs/reports/design-doc-audit.md.

## LangSmith Trace: ea9bc39e-3d80-4229-8dde-5b1296f1ebdb


## 5 Whys Analysis

Title: Ensure pipeline agents operate with current, validated design documentation

Clarity: 3 (Procedurally clear but the underlying urgency and system impact are only implicit)

5 Whys:

1. Why audit 142 design documents for validity?
   → Because many reference deleted scripts (plan-orchestrator.py) and removed conventions (tilde cost prefix), and pipeline agents read these docs when creating and executing plans, potentially causing them to follow outdated instructions.

2. Why is it problematic for autonomous agents to read stale design docs?
   → Because agents follow documented instructions literally without contextual judgment. If a design doc references a deleted function or outdated convention, the agent treats it as current truth and generates plans based on that misinformation.

3. Why have design docs become stale over time?
   → Because there's no systematic validation or sync process. As code evolves (scripts deleted, conventions removed), the design documents documenting the old architecture aren't automatically identified, updated, or removed.

4. Why hasn't someone kept the 142 docs current manually?
   → Because manual review of 142 documents is labor-intensive without automated detection of staleness. It's low-visibility work without a clear failure trigger, so it gets deferred.

5. Why is document staleness becoming a critical issue now?
   → Because the pipeline system is increasing agent autonomy. Agents now reference design docs during plan creation and execution decisions. As agent autonomy grows, the accuracy of their source material transforms from a knowledge management concern into a critical dependency for system reliability.

Root Need: Establish a reliable, validated knowledge base for increasingly autonomous pipeline agents so they make accurate plan decisions based on current architectural truth, not deleted code or removed conventions.

Summary: Stale design documentation poses an escalating risk as pipeline agents gain autonomy and depend on design docs as authoritative guidance for plan creation and execution.
