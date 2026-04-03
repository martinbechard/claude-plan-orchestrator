# Validator Skill: Plan Validation (Step 6)

## Inputs to Retrieve
- **Design Document** (design.md in workspace -- Step 5 output)
- **AC Register** (appended to requirements.md -- Step 4 output)
- **YAML Plan** (plan.yaml in workspace -- the step output)

## Cross-Reference Procedure

1. Parse the YAML plan for task entries. Each task should include a
   reference to which D\<n\> it implements and a target_acs list of
   AC\<n\> IDs it addresses.
2. For each D\<n\> in the Design Document, verify at least one task
   references it. Record any design decisions with no implementing task.
3. For each AC\<n\> in the AC Register, verify at least one task targets
   it. Record any ACs with no implementing task.
4. For each task, verify its D\<n\> reference points to an existing design
   decision and its AC\<n\> references point to existing ACs.
5. Verify task dependencies form a valid DAG (no circular dependencies).
6. Check that each task specifies file paths it will modify or create.

## Quality Gates

| Gate | Rule | How to Check | Severity |
|------|------|-------------|----------|
| QG-6.1 | Every D\<n\> has at least one task | Enumerate D IDs from design, check task refs | FAIL |
| QG-6.2 | Every AC is targeted by at least one task | Enumerate AC IDs, check task target_acs lists | FAIL |
| QG-6.3 | No task references a D\<n\> that does not exist | Look up each task's D ref in design doc | FAIL |
| QG-6.4 | No task references an AC\<n\> that does not exist | Look up each task's target_acs in AC Register | FAIL |
| QG-6.5 | Task dependencies form a valid DAG (no cycles) | Trace depends_on chains, detect cycles | FAIL |
| QG-6.6 | Each task has specific file paths | Check task descriptions for file path references | WARN |

## Lazy Plan Detection

Flag as WARN if the plan exhibits any of the following:
- Tasks that are too coarse (single task covering multiple design decisions that should be separate)
- Tasks with vague descriptions that give the implementer no concrete direction
- Missing validation tasks for code that modifies shared state or data models
- No task covering migration or backward compatibility when the design requires it
- Dependencies that would allow data-destructive tasks to run before data-preserving ones

## Verdict Derivation

- Any FAIL-severity gate violated: **FAIL**
- Only WARN-severity gates violated: **WARN**
- All gates pass: **PASS**

## Report Format

```
## Step 6 Cross-Reference: Design + ACs -> Tasks

### Design -> Task Coverage
| D<n> | Task(s) | Status |
|------|---------|--------|
| D1 | T1.1 | COVERED |
| D2 | T1.2 | COVERED |
| D3 | T2.1 | COVERED |

### AC -> Task Coverage
| AC<n> | Task(s) | Status |
|-------|---------|--------|
| AC1 | T1.1 | COVERED |
| AC2 | T1.1, T2.1 | COVERED |
| AC3 | T1.2 | COVERED |

Uncovered design decisions: <count>
Uncovered ACs: <count>
Tasks with invalid D<n> refs: <count>
Tasks with invalid AC<n> refs: <count>
Dependency cycle detected: YES/NO

## Quality Gate Results
| Gate | Result | Evidence |
|------|--------|----------|
| QG-6.1 | PASS/FAIL | <detail> |
| QG-6.2 | PASS/FAIL | <detail> |
| QG-6.3 | PASS/FAIL | <detail> |
| QG-6.4 | PASS/FAIL | <detail> |
| QG-6.5 | PASS/FAIL | <detail> |
| QG-6.6 | PASS/WARN | <detail> |

Step 6 Verdict: PASS/WARN/FAIL
```
