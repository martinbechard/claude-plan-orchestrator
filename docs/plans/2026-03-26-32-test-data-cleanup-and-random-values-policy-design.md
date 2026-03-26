# Test Data Cleanup and Random Values Policy - Design

## Overview

This defect addresses two related issues: (1) test data inserted into the production
SQLite DB during implementation was left behind, and (2) the agent policies for test
data hygiene need to be codified in the right places so the validator can enforce them.

The fix has two parts: clean up the stale test rows immediately, and ensure the policies
are already in place in both coder.md and the validator.md (Step 5c).

## Key Files to Modify

| File | Change |
|------|--------|
| SQLite DB (cost_tasks table) | Delete rows where item_slug = '12-test-item' |
| `.claude/agents/coder.md` | Verify/add Test Data Discipline section |
| `.claude/agents/validator.md` | Verify/add Step 5c test-data leak check |
| `CODING-RULES.md` | Verify/add test data policy rule |
| `plugin.json` | Patch version bump |
| `RELEASE-NOTES.md` | New entry |

## Design Decisions

**Coder.md already has the policy**: The Test Data Discipline section was added as part
of this defect's resolution. The coder agent must verify it is present and correct.

**Validator.md Step 5c**: The validator's test-data leak check must be present to catch
future violations. The coder must verify this step exists and matches the intended pattern.

**Immediate DB cleanup**: The stale row (item_slug='12-test-item') must be deleted from
the cost_tasks table before the task is marked complete. The agent must then confirm the
table has no remaining test-fixture rows.

**CODING-RULES.md**: The rule about test data cleanup belongs in the project-level coding
rules so it applies across all agents and projects using this orchestrator.
