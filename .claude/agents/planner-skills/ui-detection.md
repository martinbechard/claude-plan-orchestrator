# Planner Skill: UI Work Item Detection

Before creating implementation tasks, check whether the work item touches any file
under langgraph_pipeline/web/ (templates, static CSS/JS, or Python view handlers).

If the work item touches web UI files:

1. **Invoke the frontend-design skill** before writing any implementation tasks.
   The skill will guide you through design exploration and produce a design brief
   that the frontend-coder agent will use during implementation.
2. **Assign UI implementation tasks to the frontend-coder agent**, not coder.
3. **Add a reference to docs/ui-style-guide.md** in each frontend task description
   so the implementer reads it before making changes.

## Design Competition Process (for major UI features)

When the work item describes a significant UI redesign or multiple approaches:

1. **Produce 3 design approaches** -- each as a separate section in the design doc
   with mockup description, layout, and interaction flow.
2. **For each approach, document:**
   - How each USE CASE from the requirements is solved (reference use case by
     number, explain the user flow step by step)
   - What the user sees at each step
   - What data is needed and where it comes from
3. **Auto-judge selection** -- use the ux-reviewer agent (Opus) to evaluate all 3
   approaches against the acceptance criteria and use cases. The judge must:
   - Score each approach on: usability, completeness, alignment with use cases
   - Select a winner with written rationale
   - Save the judgment to the item's worker output directory
4. **After the judge picks a winner**, run the design validator (Opus) to verify
   the winning design has:
   - Acceptance criteria as YES/NO questions
   - Every use case from the requirements addressed with a specific solution
   - No vague or hand-wavy descriptions ("should be better" is not acceptable)
5. **If the design validator fails**, revise the winning design to add missing
   criteria or use case solutions before creating implementation tasks.

Trigger phrase to include in frontend task descriptions:
  "Style guide: docs/ui-style-guide.md."
