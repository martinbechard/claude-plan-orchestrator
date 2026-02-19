# Verification Block Template

## Purpose

Verification blocks are structured sections embedded in functional specification files.
They tell the validator agent which E2E tests verify each requirement, and provide
enough context to understand what is being tested without reading the test file.

When the validator runs after a coder task, it reads the functional spec files that
changed, finds all verification blocks, and runs the referenced E2E tests. Results
are captured in timestamped JSON log files for later analysis.

---

## Block Format

Place a verification block at the end of each requirement section:

```
### Verification

**Type:** Testable | Non-E2E | Blocked
**Test file(s):** <path to test file(s), comma-separated for multiple>
**Status:** Pass | Fail | Missing
**Scenario:** <description of what is being verified>
- Route: <URL route being tested>
- Steps: <human-readable test steps>
- Assertions: <what the test checks>
```

---

## Field Reference

### Type

| Value | Meaning |
|-------|---------|
| `Testable` | Has an automated E2E test. The validator will run it. |
| `Non-E2E` | Verified by other means (unit test, manual review, code inspection). The validator skips E2E execution. |
| `Blocked` | No UI or API exists yet; the test cannot be written. The validator skips E2E execution. |

Only `Testable` blocks trigger E2E test execution.

### Test file(s)

Path relative to the project root. Use commas to separate multiple test files:

```
**Test file(s):** tests/DG01-diagnostics-page-loads.spec.ts
**Test file(s):** tests/DG01-diagnostics-page-loads.spec.ts, tests/DG02-diagnostics-detail.spec.ts
```

Omit this field for `Non-E2E` and `Blocked` blocks.

### Status

| Value | Meaning |
|-------|---------|
| `Pass` | Test file exists and all assertions pass. |
| `Fail` | Test file exists but one or more assertions are failing. |
| `Missing` | Test file is referenced but does not exist on disk yet. |

The validator updates this field based on actual test execution results.

### Scenario, Route, Steps, Assertions

Human-readable description of what is being verified. These fields help reviewers
understand coverage without reading the test file. They are not parsed by the
validator but are included in E2E log summaries.

---

## Examples

### Example 1 — Testable block (diagnostics page load)

```
### Verification

**Type:** Testable
**Test file(s):** tests/DG01-diagnostics-page-loads.spec.ts
**Status:** Pass
**Scenario:** Verify the diagnostics list page loads and shows the data table.
- Route: /admin/diagnostics
- Steps: Sign in as admin, navigate to the diagnostics page
- Assertions: Page title is visible, data table is rendered, at least one row exists
```

### Example 2 — Non-E2E block (server-side validation)

```
### Verification

**Type:** Non-E2E
**Status:** Pass
**Scenario:** Server rejects a diagnostics submission with a missing required field.
- Route: POST /api/diagnostics
- Steps: Send a POST request with the required field omitted
- Assertions: Response status is 400, error message identifies the missing field
```

No `Test file(s)` field is needed. The validator skips this block and notes that
coverage is provided by unit tests or API-level testing.

### Example 3 — Blocked block (feature pending implementation)

```
### Verification

**Type:** Blocked
**Status:** Missing
**Scenario:** Export diagnostics data as a CSV file.
- Route: /admin/diagnostics/export
- Steps: Click the Export button on the diagnostics list page
- Assertions: A CSV file is downloaded containing all visible rows
```

No `Test file(s)` field is needed. The validator skips this block and records it
as blocked. Once the feature is implemented, change `Type` to `Testable` and add
the test file reference.
