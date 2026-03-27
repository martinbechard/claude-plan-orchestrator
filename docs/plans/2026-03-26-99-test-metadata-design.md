# Test Trace Metadata and Velocity Verification

> **For Claude:** REQUIRED SUB-SKILL: Use the implement skill to execute this plan task-by-task.

**Goal:** Verify that the recent trace metadata fix (direct proxy DB writes) correctly captures real token counts through the full observability chain.

**Architecture:** This is a trivial code change (adding a comment marker to paths.py) that triggers a real pipeline execution. The value is in the post-execution verification: checking that traces contain real token counts (not defaults/NULLs), the velocity badge renders, and completions have non-zero tokens_per_minute. The single task adds the comment and lets the validator confirm end-to-end data flow.

**Tech Stack:** Python, SQLite (proxy DB), Next.js (item detail page)

---

## Phase 1: Add Comment Marker and Verify

### Task 1.1: Add metadata test comment to paths.py

**Files:**
- Modify: `langgraph_pipeline/shared/paths.py`

**Steps:**
1. Add `# metadata test` comment after the existing header comment block
2. The validator will check acceptance criteria from the work item:
   - traces DB has execute_task row with input_tokens > 100 and output_tokens > 100
   - item detail page shows velocity badge with non-zero value
   - completions table has tokens_per_minute > 0
