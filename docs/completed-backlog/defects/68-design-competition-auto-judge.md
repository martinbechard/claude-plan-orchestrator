# Design competitions should auto-judge with a UX design agent instead of waiting for human

## Summary

When the pipeline runs a design competition (3 mockup approaches), it
currently expects the human to select the winner before proceeding. This
blocks the pipeline and requires manual intervention.

Instead, a UX design judge agent (Opus) should evaluate the 3 designs
against the acceptance criteria and select the winner automatically.
The human can override later if they disagree, but the pipeline doesn't
block.

## How it should work

1. The planner creates 3 design mockups (as it does now)
2. A judge agent (ux-reviewer or a dedicated design-judge agent) receives
   all 3 designs plus the original requirements
3. The judge evaluates each design on: usability, completeness, alignment
   with requirements, visual clarity, and information hierarchy
4. The judge selects a winner with a written rationale
5. The pipeline proceeds with the winning design
6. The judgment and rationale are saved to the item's worker output
   so the human can review the decision

## What exists already

- The ux-designer agent has an Opus orchestrator that loops with a
  Sonnet implementer
- The ux-reviewer agent evaluates design quality
- The old pipeline had a Phase 0 design competition with 3 designs
  and a judge (referenced in docs/narrative/10-design-competitions.md)

## Acceptance Criteria

- Does the pipeline auto-judge design competitions without blocking
  for human input? YES = pass, NO = fail
- Is the winning design selected by an Opus-level agent with written
  rationale? YES = pass, NO = fail
- Is the judgment saved to the item's worker output for human review?
  YES = pass, NO = fail
- Can the human override the selection if they disagree?
  YES = pass, NO = fail




## 5 Whys Analysis

Title: Design competition pipeline blocks on human judgment

Clarity: 4

5 Whys:

1. Why does the pipeline need auto-judging for design competitions?
   - Because the pipeline currently stalls waiting for a human to manually select which of 3 design mockups is best, preventing progression to the next phase.

2. Why is it a problem to wait for human selection?
   - Because the pipeline is designed to operate autonomously without synchronous human decision points. Manual judgment creates a blocking dependency that requires human presence at a specific moment.

3. Why is autonomous operation important?
   - Because it enables the pipeline to iterate continuously on design and feature development without waiting for human availability or scheduling delays that could span hours or days.

4. Why do we need continuous iteration without human gates?
   - Because rapid feedback loops accelerate validation of design choices—the pipeline can generate multiple design candidates, automatically evaluate them, and proceed to user testing or implementation faster than manual review cycles allow.

5. Why is speed of design validation critical?
   - Because the product development cycle depends on discovering which design approach works best through rapid iteration; if design judgment becomes a synchronous bottleneck, the entire feature development pipeline stalls and learning is delayed.

Root Need: The pipeline requires autonomous design evaluation to eliminate blocking synchronous checkpoints, enabling continuous iteration and rapid learning cycles for feature development.

Summary: The underlying need isn't better design judgment—it's removing the human synchronous decision gate so the autonomous pipeline can run continuously without waiting for human availability.
