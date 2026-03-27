# Design: Item Page — Show Output Artifacts

## Summary

Add an "Output Artifacts" section to the work item detail page that lists all
files created or modified by the item. This gives users a single place to find
reports, design docs, and committed files without manually searching git history
or the filesystem.

## Architecture

### Data Sources

The artifact list is assembled from four sources, in this order:

1. **Git commits** — files touched by commits whose message contains the slug
   (via subprocess git log --all --grep=slug --name-only).
2. **Design doc** — the design document in docs/plans/ matching the slug
   (already resolved by _find_design_doc).
3. **Reports directory** — files in docs/reports/ whose name contains the slug.
4. **Worker output directory** — files in docs/reports/worker-output/slug/
   (already listed by _list_output_files, but those are console logs; this
   section focuses on non-log artifacts).

### Implementation Approach

- Add a new helper function _collect_output_artifacts(slug) in
  langgraph_pipeline/web/routes/item.py that gathers artifacts from all four
  sources, deduplicates by path, and returns a list of dicts with keys:
  path (str), source (str — "git", "design", "report", "worker-output"),
  and display_name (str — basename or relative path).

- Pass the artifacts list to the template as output_artifacts.

- Add a new collapsible "Output Artifacts" section in item.html, placed
  between the Plan Tasks section and the Completions section. Each artifact
  is rendered as a file path (not a link, since this is a local dev tool
  and files are on disk).

### Key Files to Modify

- langgraph_pipeline/web/routes/item.py — add _collect_output_artifacts(),
  wire into item_detail endpoint
- langgraph_pipeline/web/templates/item.html — add Output Artifacts section

### Design Decisions

- Use subprocess to call git log rather than a git library, consistent with
  the rest of the codebase (langgraph_pipeline/shared/git.py uses subprocess).
- Deduplicate artifacts by resolved path to avoid showing the same file from
  multiple sources.
- Show the source tag (git/design/report) so users know where each artifact
  was discovered.
- Keep the section collapsed by default (like Console Output) to avoid
  cluttering the page when the list is long.
- Do not make paths clickable links since this is a local tool; plain file
  paths are sufficient and the user can open them in their editor.
