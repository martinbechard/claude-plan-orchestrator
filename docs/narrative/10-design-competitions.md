# Chapter 10: Design Competitions --- The Evolving Implement Skill

**Period:** 2026-02-07 through 2026-02-12 (refined across 7 plans)
**Pattern:** Phase 0 Design Competition + Judge

## The Problem with Single-Design Planning

Early orchestrator plans followed a straightforward pattern: write a design document,
then the orchestrator executes the implementation. This worked for backend features
(database schemas, API routes, data pipelines) where the "right" approach is often obvious
from the constraints.

But UI features were different. When building the Conversation Viewer, there were at least
five legitimate approaches: chat bubbles, notebook cells, accordion panels, split columns,
timeline cards. Each had different strengths depending on what you optimized for. Picking
one upfront was a high-stakes design decision with limited information, and a single
Claude session couldn't explore its full breadth of pattern knowledge.

The insight: **an LLM can generate multiple competing designs faster than a human can
evaluate one.** Five parallel Claude sessions each producing a complete design document
takes the same wall-clock time as one. The judging step then has real options to evaluate
instead of rubber-stamping the only proposal.

## The Phase 0 Pattern

The design competition became a standard "Phase 0" that precedes any implementation work.
It has three stages:

### Stage 1: Parallel Design Generation (Tasks 0.1 through 0.5)

Five Claude sessions run simultaneously, each given:
- The same codebase context (key source files, existing patterns)
- The same design overview document (goals, constraints, evaluation criteria)
- A **unique design concept** to explore (specified in the task description)
- A **unique output file** to write to (avoiding worktree conflicts)

```yaml
sections:
- id: phase-0
  name: 'Phase 0: Preplanning - Design Generation & Evaluation'
  status: pending
  tasks:
  - id: '0.1'
    name: Generate UI Design 1 - Chat Bubble Layout
    description: |
      Create a detailed design for the messaging interface using a chat bubble layout.
      CONTEXT: Read these files:
      - src/components/community/messages/MessageList.tsx (current display)
      - src/lib/db/messages.ts (data model)
      - docs/plans/2026-02-15-messaging-design.md (design overview with eval criteria)
      - procedure-coding-rules.md (coding standards)
      DESIGN CONCEPT: Chat-style bubbles with sender avatars, timestamps,
      and reply threading. Left-aligned for others, right-aligned for self.
      OUTPUT: Write to docs/plans/msg-design-1-chat-bubbles.md with:
      - ASCII wireframes showing the layout in various states
      - TypeScript interfaces for all components
      - Component hierarchy
      - Integration approach for existing components
      - Edge cases (long messages, images, empty states)
      IMPORTANT: Write ONLY to docs/plans/msg-design-1-chat-bubbles.md.
    status: pending
    parallel_group: phase-0-designs
  - id: '0.2'
    name: Generate UI Design 2 - Threaded Forum Layout
    description: |
      ...same context, different concept: threaded forum with collapsible replies...
      OUTPUT: Write ONLY to docs/plans/msg-design-2-threaded-forum.md.
    status: pending
    parallel_group: phase-0-designs
  # ... designs 3, 4, 5 follow the same pattern ...
```

Key design decisions:

**Five designs, not three.** Three designs tends to produce a "safe middle" and two
extremes. Five gives enough variety that genuinely creative approaches emerge. In the
file-references competition, the winning Pill Badge design beat out an Annotated Paths
approach that no human had considered.

**Each design writes to its own file.** This is critical for parallel execution. All five
tasks are in the same `parallel_group`, so they run concurrently in git worktrees. If they
wrote to the same file, the merge would fail. One file per design also makes the judge's
job easier --- it reads five self-contained documents.

**Rich design documents, not sketches.** Each design agent produces: ASCII wireframes,
TypeScript interfaces, component hierarchies, integration approaches, and edge case
analysis. This gives the judge enough detail to make an informed comparison, and gives the
implementation phase a solid specification to work from.

**Same context, different concept.** Every design agent reads the same source files and
design overview, ensuring designs are grounded in the actual codebase. The differentiation
comes from the DESIGN CONCEPT paragraph, which frames a different visual/interaction
paradigm for each.

### Stage 2: The Judge (Task 0.6)

After all five designs complete (enforced by `depends_on`), a single Claude session reads
all five documents and scores them:

```yaml
  - id: '0.6'
    name: Judge and select best design
    description: |
      Read all 5 design documents and evaluate them against the criteria
      defined in the design overview document. Select the winning design.

      Read these files:
      - docs/plans/2026-02-15-messaging-design.md (evaluation criteria)
      - docs/plans/msg-design-1-chat-bubbles.md
      - docs/plans/msg-design-2-threaded-forum.md
      - docs/plans/msg-design-3-card-stream.md
      - docs/plans/msg-design-4-split-pane.md
      - docs/plans/msg-design-5-timeline.md

      Evaluate each design against the 5 criteria (Readability, Mobile UX,
      Scalability, Implementation, Aesthetics) scoring each out of 10.
      Total is out of 50.

      Consider:
      - Does it work on mobile AND desktop?
      - Can one component serve all message types (text, image, help listing)?
      - How much refactoring of existing components is needed?
      - Is the visual language learnable without documentation?
      - Does it handle edge cases gracefully?

      After scoring, declare the winner and list 2-3 improvements
      from runner-ups to incorporate.

      Update the design overview doc with:
      - Scoring table
      - Winner declaration
      - Improvements to incorporate
      - Final design summary
    status: pending
    depends_on:
    - '0.1'
    - '0.2'
    - '0.3'
    - '0.4'
    - '0.5'
```

The judge is a single sequential task, not parallel. It needs to compare all five designs
simultaneously, which requires reading them all into one context window. The evaluation
criteria are defined in the design overview document (written by the human before
the plan starts), ensuring the judge evaluates against the project's actual priorities.

**Scoring matrix.** Each design is scored on 5 criteria (10 points each, 50 total). The
criteria vary by feature type:
- **UI features:** Clarity, Space Efficiency, Consistency, Implementation Feasibility,
  Discoverability
- **Data features:** Accuracy, Performance, Scalability, Implementation Feasibility,
  Maintainability

**Cross-pollination.** The judge doesn't just pick a winner --- it identifies 2-3
improvements from runner-up designs to incorporate into the winning design. In the file
references competition, the Pill Badge winner (43/50) incorporated inline alignment from
the Chip Tags design and compact dot indicators from the Icon Grid design.

### Stage 3: Plan Extension (Task 0.7)

The final Phase 0 task reads the winning design and extends the YAML plan with
implementation phases:

```yaml
  - id: '0.7'
    name: Extend plan with implementation tasks
    description: |
      Read the winning design and extend THIS YAML plan file with
      implementation phases.

      MANDATORY CHANGE WORKFLOW ORDER:
      1. Phase 1: Functional specification
      2. Phase 2: End-user documentation
      3. Phase 3: Backend (data models, services)
      4. Phase 4: Frontend components
      5. Phase 5: Integration (wire into existing pages)
      6. Phase 6: Unit tests
      7. Phase 7: E2E tests

      CRITICAL: The plan extension MUST be written as valid YAML.
      Append new section entries to the sections array.
    status: pending
    depends_on:
    - '0.6'
```

This task sets `plan_modified: true` in its status file, triggering the orchestrator to
reload the YAML and continue with the newly added implementation phases. The plan
effectively writes its own second half.

## The Self-Extending Plan

This pattern creates a two-phase execution:

```
Phase 0: Design Competition (written by human)
  0.1-0.5  Generate 5 designs (parallel)
  0.6      Judge and pick winner (sequential)
  0.7      Extend YAML with implementation tasks (sequential, sets plan_modified=true)

Phases 1-7: Implementation (written by task 0.7)
  ...tasks appended by the plan-extension task...
```

Phase 0 (7 tasks) is a template that can be reused across features --- it follows the
same structure every time. Claude writes Phases 1-7 (typically 15-40 tasks) based on
the winning design. The orchestrator executes all of them seamlessly, reloading the plan
when it detects the `plan_modified` flag.

This means no human reviews the detailed implementation plan. The design competition
itself is the validation: five approaches are explored, the best is selected by an AI
judge with explicit criteria, and the implementation plan flows from the winning design.
The human only intervenes if the circuit breaker trips or smoke tests fail after
completion.

This is a form of meta-programming: the AI is programming its own future execution plan
based on a design it selected from options it generated.

## Results Across 7 Plans

The design competition pattern was used for every UI feature after its introduction:

| Feature | Designs | Winner | Score | Runner-up | Score |
|---------|---------|--------|-------|-----------|-------|
| File References | 5 | Pill Badges | 43/50 | Chip Tags | 38/50 |
| Conversation Viewer | 5 | Timeline Cards | 44/50 | Notebook Cells | 40/50 |
| Forked Execution UI | 5 | Branch Tree | 41/50 | Tab Panels | 37/50 |
| Step Test Mode | 5 | Inline Test Panel | 42/50 | Split Editor | 39/50 |
| Output Rendering | 5 | Document Renderer | 45/50 | Card Gallery | 38/50 |
| Activity Feed Widget | 5 | Embed Card | 43/50 | Floating Widget | 36/50 |
| Community Dashboard | 5 | Sidebar Navigator | 40/50 | Grid Overview | 38/50 |

The pattern consistently produced winning designs that scored 40+ out of 50, with clear
differentiation from runner-ups. More importantly, the winning design often incorporated
ideas from 2-3 runner-ups, producing a richer final specification than any single
design would have been.

## Evolution of the Pattern

The competition pattern evolved through use:

**v1 (Friendly File References):** First use. Five designs, explicit evaluation criteria in
the design overview, separate judge task. Detailed DESIGN CONCEPT paragraphs were written
for each design agent to ensure diversity.

**v2 (Conversation Viewer onward):** Standardized the structure. The design overview document
always includes an "Evaluation Criteria" section with exactly 5 criteria scored out of 10.
The judge task always produces a scoring table and cross-pollination suggestions.

**v3 (Step Test Mode onward):** Added the plan-extension task (0.7) as a standard part of
Phase 0, making the transition from design to implementation seamless.

## The Implement Skill's Role

The implement skill (`.claude/skills/implement/SKILL.md`) evolved alongside this pattern.
Key additions:

**Agent team awareness.** Tasks can now specify `execution_mode: agent_team` for tasks
where multiple Claude instances need to collaborate (discuss interfaces, challenge
assumptions). This is different from `parallel_group`, where tasks are independent.

**Execution strategy decision guide.** The skill now includes a matrix helping plan authors
choose between single-agent, independent-parallel, and agent-team execution:

| Strategy | When to Use |
|----------|-------------|
| Single agent | One focused job, no coordination needed |
| Independent parallel | Different files, no communication needed |
| Agent team | Agents need to discuss, critique, or coordinate |

**Design competitions fit the independent-parallel strategy** --- each design agent works in
isolation on its own output file. The judge is a single agent that synthesizes the results.

## Cost Considerations

The design competition pattern is not cheap. Five parallel design sessions plus a judge
session means 6 Claude invocations before any implementation begins. For a typical UI
feature:

- 5 design sessions: ~$0.15-0.25 each = $0.75-1.25 total
- 1 judge session: ~$0.10-0.15
- Total Phase 0 cost: ~$0.85-1.40

However, this investment pays for itself by:
1. **Avoiding design dead-ends.** A bad design choice discovered during Phase 3
   implementation is far more expensive to fix than spending $1 on Phase 0 exploration.
2. **Producing richer specifications.** The winning design + cross-pollinated improvements
   gives the implementation agent more detailed instructions, reducing ambiguity and rework.
3. **Running in parallel.** The 5 design sessions take the same wall-clock time as 1,
   so the time cost is minimal.

## Questions

**Q: Why 5 designs? Could 3 or 10 work?**
Three designs often converge on similar approaches (the design space isn't explored
broadly enough). Ten designs exceed a single judge session's ability to compare
meaningfully --- the context window fills with design documents, leaving less room for
analysis. Five is the empirical sweet spot: enough variety to surface creative solutions,
few enough for careful comparison.

**Q: Does the judge always pick the best design?**
The judge evaluates against explicit criteria, which reduces subjectivity. However, it can
only evaluate what's in the design documents --- if a design agent produced a weak
specification for a strong concept, the judge may underrate it. The cross-pollination step
partially compensates for this by extracting good ideas from lower-scoring designs.

**Q: Could the designs compete in implementation too?**
In theory, you could implement all 5 designs and pick the best rendered version. In
practice, 5 parallel implementations would be extremely expensive and most of the work
would be thrown away. The document-level competition is a much better cost/quality tradeoff.

**Q: What if the judge picks a poor design?**
In practice, the explicit scoring criteria keep the judge honest --- it has to justify each
score against the criteria defined in the design overview. The cross-pollination step also
compensates: even if the top-ranked design isn't perfect, improvements from runner-ups are
incorporated. If the system does go off-track, the circuit breaker will trip during
implementation (build failures, test failures) and the human can investigate. The
orchestrator's `--single-task` mode makes it easy to run through 0.6, inspect the judge's
decision, and optionally edit the design doc before continuing.

**Q: Could this pattern apply to non-UI features?**
Yes. Any feature with multiple valid approaches benefits from design competition: database
schema designs, API architectures, algorithm strategies, testing approaches. The criteria
change (performance vs readability vs maintainability) but the structure is identical.
