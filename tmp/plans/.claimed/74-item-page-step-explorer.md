# Item page: step-based explorer with collapsible artifacts

The work item detail page displays all artifacts in a single long page, making it hard to navigate. The content should be organized as a step explorer showing the pipeline stages in order, with artifacts nested under each stage and loaded on demand.

## Current problem

All sections (raw input, clause register, 5 whys, structured requirements, design, plan, validation reports, execution logs) are dumped at once in a long page. There is no visual hierarchy showing which pipeline stage produced each artifact, no timestamps, and no way to collapse sections you're not interested in.

## Desired behavior

Organize artifacts under their pipeline stages in chronological order:

1. **Intake** - User request (raw input), clause register, 5 whys analysis
2. **Requirements** - Structured requirements document
3. **Planning** - Design document, YAML plan
4. **Execution** - Per-task results, validation reports
5. **Verification** - Final verification report (defects only)
6. **Archive** - Completion status, outcome

Each stage should be a collapsible section showing:
- Stage name and status (not started / in progress / done)
- Timestamp of when the stage completed
- Artifacts nested underneath, each with its own timestamp
- Artifacts loaded on demand (not all at page load) to keep the page fast

Each artifact document should display a timestamp showing when it was created or last modified.

The "Raw Input" section should be renamed to "User Request" since that is what it is.

## LangSmith Trace: n/a




## 5 Whys Analysis

Title: Item page navigation requires hierarchical stage-based artifact organization

Clarity: 5/5 (exceptionally clear problem statement, desired behavior, and acceptance criteria)

5 Whys:

W1: Why is the current item detail page hard to navigate?
    Because all artifacts are displayed in a single long page without visual hierarchy or the ability to collapse sections [C1, C3, C4]

W2: Why does a flat, unstructured layout make navigation difficult?
    Because users cannot easily identify which pipeline stage produced each artifact or understand the temporal sequence of work [C4, C5]

W3: Why do users need to understand which stage produced each artifact?
    Because each stage (Intake → Requirements → Planning → Execution → Verification → Archive) represents a distinct phase with its own outputs and context [C6, C7, C8, C9, C10, C11], and this sequence is essential to understanding why decisions were made and what work was done [ASSUMPTION]

W4: Why should artifacts load on-demand rather than all at once?
    Because when all artifacts load together, the page becomes slow to render and overwhelming to read [C15], forcing users to scroll through irrelevant sections to find what they need [ASSUMPTION: that page performance and cognitive load are pain points]

W5: Why is on-demand loading and collapsibility more important than just better visual formatting?
    Because work items accumulate many artifacts across multiple stages, and users typically need to focus on specific stages for their current task—providing instant access to relevant sections eliminates friction and prevents information overload [ASSUMPTION: that typical usage is task-focused rather than comprehensive review]

Root Need: Users need artifacts organized hierarchically by pipeline stage [C1, C2, C5] with timestamps [C12, C13, C14, C16] and on-demand loading [C15], enabling them to navigate efficiently to relevant information without cognitive overload or page performance degradation.

Summary: The root need is restructuring the item page to present artifacts grouped by pipeline stage with lazy loading, allowing users to focus on relevant work context without navigating a sprawling document.

## LangSmith Trace: b4f372ec-caae-4bc7-b6d3-81dc1d90b6ec
