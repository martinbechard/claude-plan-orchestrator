# Validator Skill: Design Validation (Step 5)

## Inputs to Retrieve
- **Structured Requirements** (requirements.md in workspace -- Step 3 output)
- **AC Register** (appended to requirements.md -- Step 4 output)
- **Design Document** (design.md in workspace -- the step output)

## Cross-Reference Procedure

1. Parse the Design Document for numbered design decisions (D1, D2, ...).
   Each D\<n\> should declare which UC/P/FR it addresses and which AC\<n\>
   it satisfies.
2. For each UC/P/FR requirement, verify at least one D\<n\> addresses it.
   Record any requirements with no design coverage.
3. For each AC\<n\> in the AC Register, verify it is reachable through at
   least one D\<n\>. "Reachable" means the D\<n\> declares that AC in its
   "Satisfies" list.
4. For each D\<n\>, verify it addresses at least one valid UC/P/FR (no
   orphaned design decisions solving problems that do not exist).
5. Check the Design -> AC traceability grid for completeness: every cell
   that should have an entry has one, and no AC column is empty.
6. For file paths mentioned in design decisions, verify they reference
   existing files or are clearly marked as "(new)" for files to be created.

## Quality Gates

| Gate | Rule | How to Check | Severity |
|------|------|-------------|----------|
| QG-5.1 | Every UC/P/FR has at least one D\<n\> | Enumerate requirements, check design coverage | FAIL |
| QG-5.2 | Every AC is reachable through at least one D\<n\> | Enumerate ACs, check design satisfies lists | FAIL |
| QG-5.3 | No D\<n\> is orphaned (every D addresses a UC/P/FR) | Check each D's "Addresses" field for valid refs | WARN |
| QG-5.4 | Design -> AC traceability grid is complete | No AC columns empty in the grid | FAIL |
| QG-5.5 | File paths reference real files or clearly mark "(new)" | Grep for file paths, check existence | WARN |

## Lazy Design Detection

Flag as WARN if the design exhibits any of the following:
- A design decision that masks a symptom instead of addressing the root cause
- Data discarded or overwritten where it should be accumulated or preserved
- Missing error/edge-case handling that real usage would require
- Shallow solutions that technically satisfy the AC text but would not hold up in practice
- Over-reliance on happy-path assumptions with no degradation strategy

## Verdict Derivation

- Any FAIL-severity gate violated: **FAIL**
- Only WARN-severity gates violated: **WARN**
- All gates pass: **PASS**

## Report Format

```
## Step 5 Cross-Reference: Requirements + ACs -> Design

### Requirement -> Design Coverage
| Requirement | D<n> | Status |
|-------------|------|--------|
| UC1 | D1, D3 | COVERED |
| P1 | D1 | COVERED |
| P2 | D2 | COVERED |

### AC -> Design Coverage
| AC<n> | D<n> | Approach | Status |
|-------|------|----------|--------|
| AC1 | D1 | <approach summary> | COVERED |
| AC2 | D1, D3 | <approach summary> | COVERED |
| AC3 | D2 | <approach summary> | COVERED |

Uncovered requirements: <count>
Uncovered ACs: <count>
Orphaned design decisions: <count>
File paths checked: <count> exist, <count> marked new, <count> missing

## Quality Gate Results
| Gate | Result | Evidence |
|------|--------|----------|
| QG-5.1 | PASS/FAIL | <detail> |
| QG-5.2 | PASS/FAIL | <detail> |
| QG-5.3 | PASS/WARN | <detail> |
| QG-5.4 | PASS/FAIL | <detail> |
| QG-5.5 | PASS/WARN | <detail> |

Step 5 Verdict: PASS/WARN/FAIL
```
