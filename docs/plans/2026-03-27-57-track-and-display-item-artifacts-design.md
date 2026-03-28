# Design: Track and Display Item Artifacts

## Summary

Enhance the work item detail page to actively track artifacts produced by
workers and display them with metadata, clickable paths, and inline content
viewing. Builds on feature 56 which added passive artifact discovery.

## Architecture

### Current State (Feature 56)

Feature 56 added _collect_output_artifacts() which discovers artifacts at
page-load time from four sources: git commits, design docs, reports directory,
and worker-output directory. Artifacts are displayed as plain text paths with
source badges. No file metadata, no clickable links, no inline viewing.

### Enhancement (Feature 57)

Three additions on top of feature 56:

1. **Artifact manifest** -- workers record created/modified files in a manifest
   JSON file at docs/reports/worker-output/<slug>/artifacts.json. Each entry
   has: path, action (created/modified), timestamp, task_id.

2. **Metadata enrichment** -- _collect_output_artifacts() merges manifest data
   with existing discovery results. Adds file_size and action (created/modified)
   to each artifact dict. Falls back to discovery-only when no manifest exists.

3. **Inline content viewer** -- new API endpoint GET /item/<slug>/artifact-content
   accepts a file path query param, reads the file, and returns its content.
   The frontend renders clickable artifact paths. For text files (.md, .json,
   .txt, .yaml, .py, .ts, .html, .css, .log), clicking opens a scrollable
   panel showing file content inline. For other file types, clicking shows
   the raw path for the user to open locally.

### Data Flow

Worker execution (task_runner.py):
  -> On commit/file-write, append entry to artifacts.json manifest

Page load (item.py):
  -> _collect_output_artifacts() reads manifest + discovery sources
  -> Merges, deduplicates, enriches with file_size
  -> Passes enriched list to template

User clicks artifact (item.html + JS):
  -> Fetch GET /item/<slug>/artifact-content?path=<relative_path>
  -> Display response in scrollable panel below the artifact entry

### Key Files to Create/Modify

- **langgraph_pipeline/shared/artifact_manifest.py** -- new module for
  reading/writing the artifact manifest JSON file. Functions:
  record_artifact(slug, path, action, task_id) and load_manifest(slug).

- **langgraph_pipeline/executor/nodes/task_runner.py** -- wire artifact
  recording into the worker execution lifecycle. After copy_worktree_artifacts
  returns files_copied, record each file in the manifest.

- **langgraph_pipeline/web/routes/item.py** -- enhance
  _collect_output_artifacts() to load manifest data and merge it with
  discovery results. Add action and file_size fields. Add new endpoint
  for serving artifact content.

- **langgraph_pipeline/web/templates/item.html** -- enhance Output Artifacts
  section: show file size and action badge, make paths clickable, add
  inline content viewer panel with JS fetch logic.

### Design Decisions

- **Option B (manifest)** chosen over git-parsing because it is simpler,
  faster at page load, and captures the action type (created vs modified)
  which git log alone does not distinguish clearly.

- **Manifest location** in docs/reports/worker-output/<slug>/artifacts.json
  reuses the existing per-slug output directory. No new directory structure.

- **Backward compatibility** -- if no manifest exists (older items), the
  existing discovery logic still works. Manifest data enriches but does
  not replace discovery.

- **Content serving** uses a new endpoint rather than static file serving
  because artifact paths may be outside the web server static directory
  and need path-traversal protection.

- **Path safety** -- the artifact-content endpoint validates that the
  requested path is within the project root directory to prevent directory
  traversal attacks.

## Acceptance Criteria

- After a worker creates a report file, does the item page list it in
  an Artifacts section with size and action type? YES = pass, NO = fail
- Can the user click on an artifact to view its content inline?
  YES = pass, NO = fail
- Does the artifacts list include the design doc, validation results,
  and any report files created by the item? YES = pass, NO = fail
