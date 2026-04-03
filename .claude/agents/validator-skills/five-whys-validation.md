# Validator Skill: 5 Whys Validation (Step 2)

## Inputs to Retrieve
- **Clause Register** (clauses.md in workspace -- Step 1 output)
- **5 Whys Analysis** (five-whys.md in workspace -- the step output)

## Cross-Reference Procedure

1. For each W\<n\> in the 5 Whys, extract the clause references (C\<n\> IDs).
2. Verify every referenced C\<n\> exists in the Clause Register. Record any
   broken references.
3. Check if any W\<n\> introduces information not present in any clause.
   If so, it MUST be flagged as an assumption in the analysis. If it is
   not flagged, this is a quality gate failure.
4. Evaluate causal coherence: does each W logically follow from the
   previous W? Record coherence assessment for each pair.
5. Verify the Root Need statement references at least one C-PROB clause
   and at least one C-GOAL clause from the register.
6. Count the number of Whys -- exactly 5 are expected (W1 through W5).

## Quality Gates

| Gate | Rule | How to Check | Severity |
|------|------|-------------|----------|
| QG-2.1 | Every W references at least one C\<n\> | Parse W entries for clause refs; flag any W with zero refs | WARN |
| QG-2.2 | All referenced C\<n\> IDs exist in the Clause Register | Look up each referenced ID in the register | FAIL |
| QG-2.3 | Causal chain is logically coherent | Each W should follow from the previous -- flag non-sequiturs | WARN |
| QG-2.4 | Root Need references at least one C-PROB and one C-GOAL | Parse Root Need for clause refs, check types in register | FAIL |
| QG-2.5 | Any W introducing info not in any clause is flagged as assumption | Check for new information and verify it is marked | FAIL |
| QG-2.6 | Exactly 5 Whys are present (W1..W5) | Count W entries | WARN |

## Verdict Derivation

- Any FAIL-severity gate violated: **FAIL**
- Only WARN-severity gates violated: **WARN**
- All gates pass: **PASS**

## Report Format

```
## Step 2 Cross-Reference: Clauses -> 5 Whys

| W<n> | Referenced Clauses | Clauses Exist? | New Info? | Coherent? |
|------|--------------------|----------------|-----------|-----------|
| W1 | C5 | YES | NO | -- (start) |
| W2 | C6, C7 | YES | NO | YES |
| W3 | C9 | YES | NO | YES |
| W4 | C8 | YES | NO | YES |
| W5 | (none) | -- | YES: flagged | YES |

Root Need references: C1 [PROB], C4 [GOAL] -- both exist: YES/NO
New information flags: <count> (<detail>)
Why count: <count>/5

## Quality Gate Results
| Gate | Result | Evidence |
|------|--------|----------|
| QG-2.1 | PASS/WARN | <detail> |
| QG-2.2 | PASS/FAIL | <detail> |
| QG-2.3 | PASS/WARN | <detail> |
| QG-2.4 | PASS/FAIL | <detail> |
| QG-2.5 | PASS/FAIL | <detail> |
| QG-2.6 | PASS/WARN | <detail> |

Step 2 Verdict: PASS/WARN/FAIL
```
