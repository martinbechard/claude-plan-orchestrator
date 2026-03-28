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
