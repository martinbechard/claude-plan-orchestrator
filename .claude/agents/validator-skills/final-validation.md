# Validator Skill: Final Item-Level Validation (Step 8)

## Purpose

After ALL tasks complete, run one final validation pass checking EVERY AC\<n\>
against the current system state. This is the archival gate. Also produce the
full end-to-end traceability matrix.

## Inputs to Retrieve
- **Clause Register** (clauses.md in workspace)
- **5 Whys Analysis** (five-whys.md in workspace)
- **Structured Requirements** (requirements.md in workspace)
- **AC Register** (appended to requirements.md)
- **Design Document** (design.md in workspace)
- **YAML Plan** (plan.yaml in workspace)
- **Per-Task Validation Reports** (validation/task-*.json in workspace)
- **Current system state** (live pages, DB, code)

## Cross-Reference Procedure

1. Read the AC Register. Enumerate EVERY AC\<n\> -- this is the complete
   checklist. Count them (this is the total).
2. For EACH AC\<n\>, verify it against the current system state:
   - Run the appropriate check (curl, Playwright, grep, DB query, etc.)
   - Record evidence (command output, file contents, page state)
   - Assign a verdict: PASS, WARN, or FAIL
3. Build the Full Traceability Matrix by tracing each clause through the
   entire chain:
   - C\<n\> -> UC/P/FR (from requirements coverage grid)
   - UC/P/FR -> AC\<n\> (from AC register)
   - AC\<n\> -> D\<n\> (from design traceability grid)
   - D\<n\> -> T\<n\> (from plan task references)
   - T\<n\> -> VF verdict (from this validation pass)
4. Check that no clause is orphaned at any level in the chain.
5. Compare final findings against per-task validation findings for
   consistency -- flag any AC that was PASS per-task but FAIL in final.

## Quality Gates

| Gate | Rule | How to Check | Severity |
|------|------|-------------|----------|
| QG-8.1 | EVERY AC\<n\> in the register has a finding (no skips) | Count findings vs total ACs | FAIL |
| QG-8.2 | requirements_checked == total ACs in register | Compare counts | FAIL |
| QG-8.3 | PASS only when requirements_met == requirements_checked | Verify 100% pass rate for PASS verdict | FAIL |
| QG-8.4 | Full traceability matrix covers every C\<n\> | Check matrix rows against clause register | FAIL |
| QG-8.5 | No clause is orphaned at any level (all columns filled) | Scan matrix for empty cells in UC/P/FR, AC, D, T columns | WARN |
| QG-8.6 | Final findings consistent with per-task findings | Compare: if task said PASS but final says FAIL, flag regression | WARN |

## Verdict Derivation

- Any FAIL-severity gate violated: **FAIL**
- Only WARN-severity gates violated: **WARN**
- All gates pass AND requirements_met == requirements_checked: **PASS**

## Archival Gate

| Final Verdict | Action |
|---------------|--------|
| PASS | Archive as COMPLETE |
| WARN | Hold for human review (do NOT archive as COMPLETE) |
| FAIL | Return to create_plan for retry |

## Report Format

```
## Step 8: Final Traceability Matrix

| C<n> | Type | UC/P/FR | AC<n> | D<n> | T<n> | VF Verdict |
|------|------|---------|-------|------|------|------------|
| C1 | PROB | UC1, P1 | AC1 | D1 | T1.1 | PASS |
| C2 | FACT | P1 | AC1 | D1 | T1.1 | PASS |
| ... | ... | ... | ... | ... | ... | ... |

## Final AC Verdicts
| AC<n> | Verdict | Evidence |
|-------|---------|----------|
| AC1 | PASS | <evidence> |
| AC2 | PASS | <evidence> |
| AC3 | PASS | <evidence> |

Total ACs: <count>
Passed: <count>
requirements_checked: <count>
requirements_met: <count>

## Per-Task vs Final Consistency
| AC<n> | Task Verdict | Final Verdict | Consistent? |
|-------|-------------|---------------|-------------|
| AC1 | PASS | PASS | YES |
| ... | ... | ... | ... |

Regressions detected: <count>

## Quality Gate Results
| Gate | Result | Evidence |
|------|--------|----------|
| QG-8.1 | PASS/FAIL | <detail> |
| QG-8.2 | PASS/FAIL | <detail> |
| QG-8.3 | PASS/FAIL | <detail> |
| QG-8.4 | PASS/FAIL | <detail> |
| QG-8.5 | PASS/WARN | <detail> |
| QG-8.6 | PASS/WARN | <detail> |

Final Verdict: PASS/WARN/FAIL
```
