# Validator Skill: AC Generation Validation (Step 4)

## Inputs to Retrieve
- **Clause Register** (clauses.md in workspace -- Step 1 output)
- **Structured Requirements** (requirements.md in workspace -- Step 3 output)
- **AC Register** (appended to requirements.md -- the step output)

## AC Origin Rules

The AC Register must follow these derivation rules:

| Origin Type | Rule |
|-------------|------|
| Explicit (C-AC) | User-provided criterion preserved verbatim -- no rewording |
| Derived from C-PROB | Mechanical inverse: "X is broken" becomes "Is X working? YES/NO" |
| Derived from C-GOAL | Made testable: "user should X" becomes "Can user X? YES/NO" |

## Cross-Reference Procedure

1. Collect all C-AC clauses from the register. For each, verify it appears
   verbatim (exact wording) as an AC in the AC Register.
2. Collect all C-PROB clauses. For each, verify at least one AC is derived
   from it (mechanical inverse pattern).
3. Collect all C-GOAL clauses. For each, verify at least one AC is derived
   from it (operationalized pattern).
4. For each UC/P/FR requirement, verify at least one AC belongs to it.
5. For each AC, verify it belongs to a valid UC/P/FR (no orphaned ACs).
6. For C-FACT and C-CTX clauses that have no AC, verify an explicit
   justification is provided (e.g., "evidence for P1, covered by AC1").
7. Verify every AC statement is a YES/NO verifiable question.

## Quality Gates

| Gate | Rule | How to Check | Severity |
|------|------|-------------|----------|
| QG-4.1 | Every C-AC clause appears verbatim as an AC | Exact string match of C-AC text in AC Register | FAIL |
| QG-4.2 | Every C-PROB has at least one derived AC | Filter C-PROB clauses, check AC origins | FAIL |
| QG-4.3 | Every C-GOAL has at least one derived AC | Filter C-GOAL clauses, check AC origins | FAIL |
| QG-4.4 | Every UC/P/FR has at least one AC | Check Requirement -> AC coverage grid | FAIL |
| QG-4.5 | No AC is orphaned (every AC belongs to a UC/P/FR) | Check each AC's "Belongs to" field | WARN |
| QG-4.6 | C-FACT/C-CTX without ACs have explicit justification | Check Clause -> AC grid for justification text | WARN |
| QG-4.7 | AC statements are YES/NO verifiable questions | Each AC should end with "? YES = pass, NO = fail" or equivalent | WARN |

## Lazy AC Detection

Flag as WARN if the acceptance criteria exhibit any of the following:
- ACs that can be trivially satisfied by a stub (e.g. "Does the function exist?" instead of "Does the function produce correct results for X?")
- No ACs covering error cases or edge cases when the requirement clearly has them
- No ACs for data preservation when existing data could be affected by the change
- ACs that test presence of code rather than observable behavior

## Verdict Derivation

- Any FAIL-severity gate violated: **FAIL**
- Only WARN-severity gates violated: **WARN**
- All gates pass: **PASS**

## Report Format

```
## Step 4 Cross-Reference: Clauses + Requirements -> ACs

### Clause -> AC Coverage
| C<n> | Type | AC<n> | How Derived | Status |
|------|------|-------|-------------|--------|
| C1 | PROB | AC1 | Inverse | COVERED |
| C4 | GOAL | AC2 | Made testable | COVERED |
| C5 | CTX | -- | -- | JUSTIFIED: "context, not testable" |
| ... | ... | ... | ... | ... |

### Requirement -> AC Coverage
| Requirement | ACs | Count | Status |
|-------------|-----|-------|--------|
| UC1 | AC2 | 1 | COVERED |
| P1 | AC1 | 1 | COVERED |
| P2 | AC3 | 1 | COVERED |

C-AC clauses missing verbatim ACs: <count>
C-PROB clauses without derived ACs: <count>
C-GOAL clauses without derived ACs: <count>
Requirements without ACs: <count>
Orphaned ACs: <count>

## Quality Gate Results
| Gate | Result | Evidence |
|------|--------|----------|
| QG-4.1 | PASS/FAIL | <detail> |
| QG-4.2 | PASS/FAIL | <detail> |
| QG-4.3 | PASS/FAIL | <detail> |
| QG-4.4 | PASS/FAIL | <detail> |
| QG-4.5 | PASS/WARN | <detail> |
| QG-4.6 | PASS/WARN | <detail> |
| QG-4.7 | PASS/WARN | <detail> |

Step 4 Verdict: PASS/WARN/FAIL
```
