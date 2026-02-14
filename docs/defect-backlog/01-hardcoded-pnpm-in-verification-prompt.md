# Hardcoded pnpm Commands in Verification Prompt

## Status: Open

## Priority: Medium

## Summary

The VERIFICATION_PROMPT_TEMPLATE in scripts/auto-pipeline.py hardcodes pnpm-specific
commands (pnpm run build, pnpm test, pnpm dev). These commands are not applicable to
all projects. Since the orchestrator is designed to be project-agnostic, the verification
prompt should read build/test/dev-server commands from the orchestrator-config.yaml file,
falling back to sensible defaults only when no config exists.

## Expected Behavior

The verification prompt should use project-specific commands from orchestrator-config.yaml.
The config file already exists at .claude/orchestrator-config.yaml and already loads a
dev_server_port field. It should be extended to support:

- build_command (default: "pnpm run build")
- test_command (default: "pnpm test")
- dev_server_command (default: "pnpm dev")

The VERIFICATION_PROMPT_TEMPLATE should interpolate these values instead of hardcoding them.

## Actual Behavior

The VERIFICATION_PROMPT_TEMPLATE at line ~1057 of scripts/auto-pipeline.py contains:
- "Does pnpm run build pass?" (line ~1075)
- "Do unit tests pass? (pnpm test)" (line ~1076)
- "start it with pnpm dev" (line ~1107)

These are hardcoded strings, not derived from any configuration.

## Fix Required

1. Add build_command, test_command, and dev_server_command keys to the config loading
   logic (with defaults matching current behavior for backward compatibility).
2. Update the VERIFICATION_PROMPT_TEMPLATE to use {build_command}, {test_command}, and
   {dev_server_command} placeholders.
3. Update the verify_item() function to pass these values when formatting the prompt.
4. Update the orchestrator-config.yaml comments to document the new fields.

## Verification

- grep for "pnpm" in VERIFICATION_PROMPT_TEMPLATE - should find zero hardcoded occurrences
- Verify the config loading includes the three new keys with correct defaults
- Check that the .claude/orchestrator-config.yaml documents the new fields in comments

## Verification Log

### Verification #1 - 2026-02-13 14:30

**Verdict: PASS**

**Checks performed:**
- [x] Python syntax check passes (no build system in this project)
- [x] No unit tests exist in this project (N/A)
- [x] No hardcoded pnpm references in VERIFICATION_PROMPT_TEMPLATE
- [x] Config loading includes build_command, test_command, dev_server_command with correct defaults
- [x] orchestrator-config.yaml documents the three new fields in comments

**Findings:**

1. **VERIFICATION_PROMPT_TEMPLATE (lines 1063-1115):** Contains zero hardcoded "pnpm" strings. Lines 1081, 1082, and 1112 now use {build_command}, {test_command}, and {dev_server_command} placeholders respectively.

2. **Config loading (lines 44-46, 76-78):** Three manifest constants (DEFAULT_BUILD_COMMAND, DEFAULT_TEST_COMMAND, DEFAULT_DEV_SERVER_COMMAND) defined with correct defaults ("pnpm run build", "pnpm test", "pnpm dev"). Lines 76-78 load from _config with these defaults as fallbacks via _config.get().

3. **verify_item() function (lines 1165-1171):** The .format() call passes build_command=BUILD_COMMAND, test_command=TEST_COMMAND, and dev_server_command=DEV_SERVER_COMMAND.

4. **orchestrator-config.yaml:** All three fields are documented as comments (lines 10-17) with example values matching the defaults.

5. **Note:** Two other hardcoded "pnpm" references exist outside the defect scope -- line 666 (plan creation prompt) and line 915 (dev server restart subprocess). These are not part of VERIFICATION_PROMPT_TEMPLATE and are not covered by this defect.
