# Validator Skill: Requirements Verification (Step 5 + 5a + 5c)

## Step 5: Requirements

### AC-Traced Mode (preferred)
If the task includes a target_acs list (e.g., target_acs: ['AC1', 'AC2']),
use the AC Register as the primary checklist. For EACH AC\<n\> in target_acs:
1. Look up AC\<n\> in the AC Register (in requirements.md)
2. Verify the criterion is satisfied in the current system state
3. Record the AC ID in your finding: "[PASS] AC1: Does X work? -- verified via tests"
4. Record as a VF (Validation Finding) for the traceability matrix
5. If an AC has no matching implementation at all, that is a FAIL

### P\<n\> Mode (fallback)
If no target_acs is present but a Structured Requirements file is provided
(P1, P2, ... format), use it as the primary checklist. For EACH P\<n\>
requirement in the file:
1. Check whether the acceptance criteria for that requirement are satisfied
2. Record the P\<n\> ID in your finding: "[PASS] P1: Does X work? -- verified via tests"
3. If a requirement has no matching implementation at all, that is a FAIL

### Legacy Mode
If no Structured Requirements file is provided, extract acceptance criteria from
the work item file directly.

Missing requirements = FAIL.

### Per-Task Quality Gates (QG-7.x)

| Gate | Rule | Severity |
|------|------|----------|
| QG-7.1 | Every AC in the task's target_acs has a finding (no skips) | FAIL |
| QG-7.2 | Every finding has non-empty evidence | WARN |
| QG-7.3 | Verdict follows: PASS = 100%, WARN = < 100%, FAIL = regression | FAIL |
| QG-7.4 | Build succeeds (no regressions from baseline) | FAIL |
| QG-7.5 | Tests pass (no regressions from baseline) | FAIL |

Before concluding a requirement is satisfied, run these sub-checks:

## 5a. Placeholder scan
Grep created/modified files (and any referenced UI pages) for: TODO, not yet
available, placeholder, dummy, fake, FIXME, lorem ipsum.
Any hit = WARN. If the hit maps to an unmet acceptance criterion = FAIL.

## 5c. Test-data leak check
Grep all modified source files, DB migrations, AND production databases for
known test-fixture patterns:
- Strings: foo.py, test-item, test-slug, example.com, placeholder, dummy,
  mock_data, lorem ipsum, hardcoded
- Suspicious round numbers in data: cost=0.01, tokens=100, tokens=50,
  duration=0 in rows that claim to be real data
- If the task involves a database, query for rows that look like test fixtures
  (e.g. SELECT * FROM cost_tasks WHERE item_slug LIKE '%test%')
Any test data found in production databases or non-test files = FAIL (not WARN).
The coder is required to clean up test data before completion.
