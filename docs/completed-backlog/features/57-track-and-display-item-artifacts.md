# Track artifacts created by each work item and display them on the item page

## Summary

When a pipeline worker creates files (reports, design docs, code changes),
there is no record of what was produced. The user has to grep git history
or search directories manually to find the output. We need:

1. A mechanism to track which files an item's workers created or modified
2. A section on the item detail page listing all artifacts
3. Each artifact is a clickable link that shows the file content inline
   (for text/markdown files) or links to the raw file

## How to track artifacts

Option A: Parse git commits by the item's workers. Each worker commits
with the slug in the message. Extract changed files from those commits.

Option B: The worker records files it creates in a manifest JSON file
(e.g. docs/reports/worker-output/<slug>/artifacts.json) listing each
file path, type (created/modified), and timestamp.

Option B is simpler and doesn't require git parsing at page load time.

## Display on item page

Add an "Artifacts" section showing:
- File path (clickable)
- Type: created / modified
- Size
- Clicking opens the content in a scrollable panel (for .md, .json, .txt)
  or a download link for binary files

## Acceptance Criteria

- After a worker creates a report file, does the item page list it in
  an Artifacts section? YES = pass, NO = fail
- Can the user click on the artifact to view its content inline?
  YES = pass, NO = fail
- Does the artifacts list include the design doc, validation results,
  and any report files created by the item?
  YES = pass, NO = fail




## 5 Whys Analysis

I've checked the brainstorming skill, but I see this request is for a specific analytical method (5 Whys) applied to an already well-defined backlog item, rather than a full design brainstorming process. The item includes clear requirements, acceptance criteria, and even implementation options. Let me provide the 5 Whys analysis you requested.

---

**Title:** Understanding the root need behind artifact tracking and visibility

**Clarity:** 4/5 — The feature is well-specified with clear acceptance criteria, though the deeper *why* behind user pain isn't explicit

**5 Whys:**

1. **Why do users need to see artifacts on the item page?**
   - Workers produce files (reports, docs, code changes) but there's no discoverable record. Users must manually search git history or directory trees to find what was actually produced.

2. **Why is manual discovery a problem?**
   - The pipeline is asynchronous and distributed. A user closes an item page and hours later a worker completes tasks. Without centralized visibility, users don't know what output was generated or where to find it.

3. **Why is this visibility gap especially painful here?**
   - The item page is the natural hub where users go to understand an item's status. If artifacts aren't listed there, users have to context-switch to git logs, file explorers, or Slack notifications to find what was produced—fragmenting the workflow.

4. **Why does this context-switching cost matter to your users?**
   - The pipeline automates complex multi-step workflows (validation, design generation, implementation). Users need confidence that the work actually completed and produced valid outputs. Without artifact visibility on the item page, they can't quickly verify that or hand off results to downstream work.

5. **Why is artifact verification critical to pipeline trust?**
   - If users can't easily see what a pipeline run produced, they can't tell if it succeeded, failed silently, or produced unexpected results. This breaks the feedback loop and makes the system feel unreliable—users fall back to manual work instead of trusting the automation.

**Root Need:** Users need **immediate, centralized visibility into pipeline outputs** to verify that automated work completed correctly and to easily access results for downstream work—without leaving the item context or searching git history.

**Summary:** The feature solves a visibility and workflow fragmentation problem where asynchronous pipeline work produces outputs that users can't discover or verify from the natural hub (item page), breaking trust in the automation.
