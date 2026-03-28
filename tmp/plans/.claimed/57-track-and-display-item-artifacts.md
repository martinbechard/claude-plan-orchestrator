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

## LangSmith Trace: 3b288699-1e16-4645-9a8b-6fd370dcecc8


## 5 Whys Analysis

**Title:** Workers produce outputs with no discoverable registry

**Clarity:** 4/5
(The request clearly describes the problem and solution, but doesn't articulate *why* artifact visibility matters to the user.)

**5 Whys:**

1. **Why can't users find files created by workers?**
   Because there's no central record of what was produced. Workers create files scattered across the filesystem or buried in git history with no index.

2. **Why isn't there a record of artifacts?**
   Because the current system tracks *task execution* but not *task outputs*. Workers run, commit changes, and move on—the system has no mechanism to collect or catalog what they created.

3. **Why doesn't the worker lifecycle include artifact registration?**
   Because the original design optimized for running work and persisting changes, not for tracking evidence or making outputs discoverable as first-class items in the UI.

4. **Why is artifact visibility important enough to build into the item page?**
   Because users need to understand what each item accomplished—what evidence was generated, what reports were produced, what decisions were made—without leaving the item context.

5. **Why do users need this understanding in the first place?**
   Because artifacts are the *proof* that work happened. Without them visible, users can't audit decisions, validate outputs, understand methodology, or reuse generated documentation and reports.

**Root Need:** Users need artifact visibility to build trust in pipeline decisions and access work products without manual searching, making outputs a first-class part of the item's audit trail and decision record.

**Summary:** The pipeline produces evidence but keeps it hidden, forcing users to manually excavate outputs instead of reviewing them as part of the item's documented accomplishment.
