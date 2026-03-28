# Hardcoded pnpm Commands - Design Document

> **For Claude:** REQUIRED SUB-SKILL: Use the implement skill to execute this plan task-by-task.

**Goal:** Replace hardcoded pnpm commands in both orchestrator scripts with configurable values from orchestrator-config.yaml.

**Architecture:** Extend the existing config loading pattern (already used for dev_server_port) with three new keys: build_command, test_command, and dev_server_command. Both scripts already call load_orchestrator_config() at module level, so the new keys are read the same way. Template strings use Python .format() interpolation with the new values.

**Affected Files:**
- scripts/auto-pipeline.py - VERIFICATION_PROMPT_TEMPLATE and verify_item()
- scripts/plan-orchestrator.py - task prompt and smoke test messages
- .claude/orchestrator-config.yaml - new documented fields

---

## Phase 1: Configuration Extension

### Task 1.1: Add command config keys to auto-pipeline.py

**Files:**
- Modify: scripts/auto-pipeline.py (lines ~43, ~72)

**Design:**

Add three default constants alongside DEFAULT_DEV_SERVER_PORT:

    DEFAULT_BUILD_COMMAND = "pnpm run build"
    DEFAULT_TEST_COMMAND = "pnpm test"
    DEFAULT_DEV_SERVER_COMMAND = "pnpm dev"

Read them from _config the same way DEV_SERVER_PORT is read:

    BUILD_COMMAND = _config.get("build_command", DEFAULT_BUILD_COMMAND)
    TEST_COMMAND = _config.get("test_command", DEFAULT_TEST_COMMAND)
    DEV_SERVER_COMMAND = _config.get("dev_server_command", DEFAULT_DEV_SERVER_COMMAND)

### Task 1.2: Update VERIFICATION_PROMPT_TEMPLATE in auto-pipeline.py

**Files:**
- Modify: scripts/auto-pipeline.py (lines ~1057-1109)

**Design:**

Replace the three hardcoded pnpm references with format placeholders:

- Line ~1075: "Does pnpm run build pass?" -> "Does {build_command} pass?"
- Line ~1076: "Do unit tests pass? (pnpm test)" -> "Do unit tests pass? ({test_command})"
- Line ~1107: "start it with pnpm dev" -> "start it with {dev_server_command}"

### Task 1.3: Update verify_item() to pass new format values

**Files:**
- Modify: scripts/auto-pipeline.py (line ~1159)

**Design:**

The VERIFICATION_PROMPT_TEMPLATE.format() call currently passes item_path, slug, and count. Add the three command values:

    prompt = VERIFICATION_PROMPT_TEMPLATE.format(
        item_path=item.path,
        slug=item.slug,
        count=attempt_count,
        build_command=BUILD_COMMAND,
        test_command=TEST_COMMAND,
        dev_server_command=DEV_SERVER_COMMAND,
    )

---

## Phase 2: Plan Orchestrator Fixes

### Task 2.1: Add command config keys to plan-orchestrator.py

**Files:**
- Modify: scripts/plan-orchestrator.py (lines ~40-59)

**Design:**

Same pattern as auto-pipeline.py - add the three default constants and read from _config.

### Task 2.2: Update task prompt and smoke test messages in plan-orchestrator.py

**Files:**
- Modify: scripts/plan-orchestrator.py (lines ~1157, ~1209)

**Design:**

- Line ~1157: "Run pnpm run build to verify no TypeScript errors" -> use f-string with BUILD_COMMAND
- Line ~1209: "Start a server with 'pnpm dev'" -> use f-string with DEV_SERVER_COMMAND

Note: The task prompt is built as an f-string, not a .format() template, so use {BUILD_COMMAND} directly.

---

## Phase 3: Configuration and Verification

### Task 3.1: Update orchestrator-config.yaml with new documented fields

**Files:**
- Modify: .claude/orchestrator-config.yaml

**Design:**

Add commented-out entries documenting the new fields with their defaults:

    # Build command used for verification checks.
    # build_command: "pnpm run build"

    # Test command used for verification checks.
    # test_command: "pnpm test"

    # Dev server start command used for verification checks.
    # dev_server_command: "pnpm dev"

### Task 3.2: Regression verification

**Steps:**
1. grep for hardcoded "pnpm" in VERIFICATION_PROMPT_TEMPLATE - should find zero
2. grep for hardcoded "pnpm" in the plan-orchestrator task prompt - should find zero
3. Verify config loading includes the three new keys with correct defaults
4. Run: python scripts/plan-orchestrator.py --plan .claude/plans/sample-plan.yaml --dry-run
5. Run: python scripts/auto-pipeline.py --dry-run (if supported)
