# Test: Live Stats on Item Page

> **For Claude:** REQUIRED SUB-SKILL: Use the implement skill to execute this plan task-by-task.

**Goal:** Add a test comment to paths.py to verify that the web UI displays live Cost, Tokens, and velocity metrics while items are running.

**Architecture:** This is a simple test marker -- add the comment "# live stats test" to langgraph_pipeline/shared/paths.py. The real validation is manual: the acceptance criteria check whether the item page shows non-zero Cost/Tokens and the velocity badge during execution (not after completion).

**Tech Stack:** Python

---

## Phase 1: Implementation

### Task 1.1: Add live stats test comment

**Files:**
- Modify: `langgraph_pipeline/shared/paths.py`

**Steps:**
1. Add comment "# live stats test" to the file header area
2. Verify syntax with build command
