# Move Completed Items Outside Backlog Directories - Design Document

> **For Claude:** REQUIRED SUB-SKILL: Use the implement skill to execute this plan task-by-task.

**Goal:** Move completed backlog items out of the backlog directories into a separate
top-level archive location so that scan cycles only see open items and the completed
set does not pollute the backlog folders.

**Problem:** The auto-pipeline stores completed items in completed/ subdirectories inside
each backlog folder (docs/defect-backlog/completed/, docs/feature-backlog/completed/).
Every scan cycle reads all completed files to build a completed_slugs set, logs
"Skipping completed item" for each one, and the filesystem watcher receives events
for completed-item moves within the watched tree.

**Architecture:** Introduce a top-level docs/completed-backlog/ directory with two
subdirectories: docs/completed-backlog/defects/ and docs/completed-backlog/features/.
Update auto-pipeline.py constants and functions to read from and write to these new
locations. Physically move existing completed files to the new structure.

**Affected Files:**
- scripts/auto-pipeline.py - constants, scan_directory, completed_slugs, archive_item,
  BacklogWatcher, and related references to COMPLETED_SUBDIR

---

## Phase 1: Implementation

### Task 1.1: Update constants and path logic in auto-pipeline.py

**Files:**
- Modify: scripts/auto-pipeline.py

**Design:**

1. Replace the single COMPLETED_SUBDIR constant with two new path constants:

       COMPLETED_DEFECTS_DIR = "docs/completed-backlog/defects"
       COMPLETED_FEATURES_DIR = "docs/completed-backlog/features"

   A helper mapping from item_type to archive directory:

       COMPLETED_DIRS = {
           "defect": COMPLETED_DEFECTS_DIR,
           "feature": COMPLETED_FEATURES_DIR,
       }

2. Remove the COMPLETED_SUBDIR constant entirely (no deprecation shim).

### Task 1.2: Update completed_slugs() to read from new locations

**Files:**
- Modify: scripts/auto-pipeline.py (completed_slugs function)

**Design:**

Replace the loop over DEFECT_DIR/FEATURE_DIR with COMPLETED_SUBDIR:

    def completed_slugs() -> set[str]:
        slugs: set[str] = set()
        for completed_dir_path in [COMPLETED_DEFECTS_DIR, COMPLETED_FEATURES_DIR]:
            completed_dir = Path(completed_dir_path)
            if not completed_dir.exists():
                continue
            for md_file in completed_dir.glob("*.md"):
                slugs.add(md_file.stem)
        return slugs

### Task 1.3: Update archive_item() to write to new locations

**Files:**
- Modify: scripts/auto-pipeline.py (archive_item function)

**Design:**

Instead of building dest_dir from os.path.dirname(item.path) / COMPLETED_SUBDIR,
look up the correct archive directory from COMPLETED_DIRS based on item.item_type:

    def archive_item(item: BacklogItem, dry_run: bool = False) -> bool:
        source = item.path
        dest_dir = COMPLETED_DIRS[item.item_type]
        dest = os.path.join(dest_dir, os.path.basename(item.path))
        ...

### Task 1.4: Clean up BacklogWatcher - remove completed/ filter

**Files:**
- Modify: scripts/auto-pipeline.py (BacklogWatcher class)

**Design:**

The BacklogWatcher.on_created and on_modified methods currently filter out
events with /{COMPLETED_SUBDIR}/ in the path. Since completed items will no
longer live inside the watched directories, this filter is no longer needed.
Remove the COMPLETED_SUBDIR check from both methods. This simplifies the code
and avoids a stale reference to the removed constant.

### Task 1.5: Move existing completed files to new structure

This is a data migration step. Move files from:
- docs/defect-backlog/completed/*.md -> docs/completed-backlog/defects/
- docs/feature-backlog/completed/*.md -> docs/completed-backlog/features/

Then remove the now-empty completed/ subdirectories.

Git commit the moves so history is preserved via rename detection.

---

## Phase 2: Unit Tests

### Task 2.1: Add unit tests for updated functions

**Files:**
- Create: tests/test_completed_archive.py

**Tests to write:**
- test_completed_slugs_reads_from_new_locations: Create temp files in the new
  directory structure and verify completed_slugs() returns the correct set.
- test_archive_item_writes_to_correct_location: Verify archive_item moves defects
  to docs/completed-backlog/defects/ and features to docs/completed-backlog/features/.
- test_scan_directory_ignores_completed_items_by_status: Verify scan_directory
  still skips items with completed status in their header (unchanged behavior).

---

## Phase 3: Verification

### Task 3.1: Syntax check and dry-run validation

**Steps:**
1. Check Python syntax for both scripts
2. Run orchestrator dry-run
3. Run unit tests
4. Verify COMPLETED_SUBDIR is no longer referenced in auto-pipeline.py
5. Verify new constants exist
