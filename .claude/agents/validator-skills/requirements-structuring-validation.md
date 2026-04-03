# Validator Skill: Requirements Structuring Validation (Step 3)

## Inputs to Retrieve
- **Clause Register** (clauses.md in workspace -- Step 1 output)
- **5 Whys Analysis** (five-whys.md in workspace -- Step 2 output)
- **Structured Requirements** (requirements.md in workspace -- the step output)

## Cross-Reference Procedure

1. Parse the Clause Coverage Grid from the requirements output. For each
   C\<n\> in the Clause Register, verify it appears in the grid.
2. For each clause NOT mapped to a requirement, verify an explicit
   justification is provided in the grid (e.g., "context only, not testable").
3. For each requirement (UC\<n\>, P\<n\>, FR\<n\>), verify it has at least one
   source clause reference and that all referenced C\<n\> IDs exist.
4. For each root cause mentioned in a requirement, verify the W\<n\>
   reference points to an existing entry in the 5 Whys Analysis.
5. Verify that every C-PROB clause maps to at least one P\<n\> requirement.
6. Verify that every C-GOAL clause maps to at least one UC\<n\> or FR\<n\>.

## Requirement Type Rules

| Clause Type | Expected Requirement Type |
|-------------|--------------------------|
| C-PROB | P\<n\> (Problem) |
| C-GOAL | UC\<n\> (Use Case) or FR\<n\> (Feature Request) |
| C-FACT | May map to any type or serve as evidence |
| C-CONS | Should appear as a constraint on related requirements |
| C-CTX | May be unmapped with justification |
| C-AC | Must produce a verbatim AC in Step 4 |

## Quality Gates

| Gate | Rule | How to Check | Severity |
|------|------|-------------|----------|
| QG-3.1 | Every C\<n\> appears in the Coverage Grid | Enumerate clause IDs from register, check grid | FAIL |
| QG-3.2 | Every unmapped clause has explicit justification | Check unmapped entries in grid for explanation text | FAIL |
| QG-3.3 | Every requirement has at least one source clause reference | Parse each UC/P/FR for clause refs | FAIL |
| QG-3.4 | All source clause references point to existing C\<n\> IDs | Look up each referenced ID in register | FAIL |
| QG-3.5 | Root causes reference W\<n\> IDs that exist in 5 Whys | Parse root cause refs, look up in 5 Whys | FAIL |
| QG-3.6 | Every C-PROB maps to at least one P\<n\> | Filter C-PROB clauses, check coverage grid | FAIL |
| QG-3.7 | Every C-GOAL maps to at least one UC\<n\> or FR\<n\> | Filter C-GOAL clauses, check coverage grid | FAIL |

## Lazy Requirements Detection

Flag as WARN if the requirements exhibit any of the following:
- Requirements so vague they could be satisfied by a stub implementation
- Missing error-case or edge-case requirements when the problem clearly has them
- No data preservation/migration requirement when existing data could be affected
- Constraints from the original request dropped without justification

## Verdict Derivation

- Any FAIL-severity gate violated: **FAIL**
- Only WARN-severity gates violated: **WARN**
- All gates pass: **PASS**

## Report Format

```
## Step 3 Cross-Reference: Clauses -> Requirements

| C<n> | Type | Mapped To | In Grid? | Status |
|------|------|-----------|----------|--------|
| C1 | PROB | UC1, P1 | YES | COVERED |
| C2 | FACT | P1 | YES | COVERED |
| C5 | CTX | -- | YES | JUSTIFIED: "root cause context" |
| ... | ... | ... | ... | ... |

Unmapped clauses: <count>
Unmapped without justification: <count>
Requirements with broken clause refs: <count>
Requirements with broken W<n> refs: <count>
C-PROB clauses without P<n>: <count>
C-GOAL clauses without UC/FR: <count>

## Quality Gate Results
| Gate | Result | Evidence |
|------|--------|----------|
| QG-3.1 | PASS/FAIL | <detail> |
| QG-3.2 | PASS/FAIL | <detail> |
| QG-3.3 | PASS/FAIL | <detail> |
| QG-3.4 | PASS/FAIL | <detail> |
| QG-3.5 | PASS/FAIL | <detail> |
| QG-3.6 | PASS/WARN | <detail> |
| QG-3.7 | PASS/WARN | <detail> |

Step 3 Verdict: PASS/WARN/FAIL
```
