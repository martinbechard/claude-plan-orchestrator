# Pipeline Step Metamodel: Traceability and Validation

## Purpose

This document defines the metamodel for the pipeline's processing steps. Each step
transforms artifacts. A validation agent operates after each step, retrieving the
step's inputs and outputs to produce a cross-reference report that proves the
transformation was done correctly. Quality gates define the pass/fail criteria for
each cross-reference.

The end-to-end traceability chain is:

    Clause (C) -> Why (W) -> Requirement (UC/P/FR) -> AC -> Design (D) -> Task (T) -> Validation Finding (VF)

Every link in this chain is auditable. Coverage grids at each step prove nothing
was lost. The work item page displays all artifacts so a human can verify the chain.

---

## Glossary

### Clause Types (produced in Step 1)

| Code | Name | Definition |
|------|------|------------|
| C-PROB | Problem statement | Something broken or wrong |
| C-FACT | Observation/fact | Verifiable current state |
| C-GOAL | Desired outcome | What the user wants to be true |
| C-CONS | Constraint | Limitation on the solution |
| C-CTX | Context/background | Information that explains why |
| C-AC | Acceptance criterion | Explicit pass/fail test from the user |

### Requirement Types (produced in Step 3)

| Code | Name | Derived From |
|------|------|--------------|
| UC | Use Case | C-GOAL clauses (user workflows) |
| P | Problem | C-PROB clauses (things broken) |
| FR | Feature Request | C-GOAL clauses (new capabilities) |

### Artifact IDs

| ID Pattern | Meaning | Produced By |
|------------|---------|-------------|
| C\<n\> | Individual clause (C1, C2, ...) | Step 1 |
| W\<n\> | Why-because pair in 5 Whys chain | Step 2 |
| UC\<n\>, P\<n\>, FR\<n\> | Typed requirement | Step 3 |
| AC\<n\> | Acceptance criterion | Step 4 |
| D\<n\> | Design decision | Step 5 |
| T\<n\> | Implementation task | Step 6 |
| VF | Validation finding (per-AC verdict) | Steps 7-8 |

### Verdict Scale

| Verdict | Meaning |
|---------|---------|
| PASS | 100% of checked criteria met |
| WARN | Partial -- some criteria not fully satisfied |
| FAIL | Regression introduced, or critical criterion completely unmet |

---

## Step-by-Step Specification

### Step 1: Clause Extraction

**Pipeline node:** intake_analyze (first phase)
**Artifact:** Clause Register (clauses.md)

#### Inputs
- Raw backlog item file (markdown, unstructured)

#### Process
Parse every independently meaningful statement into a numbered clause.
Tag each by type (C-PROB, C-FACT, C-GOAL, C-CONS, C-CTX, C-AC).
Preserve exact wording -- do not paraphrase or interpret.

#### Outputs
- Clause Register with sequential IDs (C1, C2, ...)
- Each clause has: ID, type code, original text
- Summary: total clause count and breakdown by type

#### Validation Cross-Reference Report

The validator retrieves:
- **Input:** Raw backlog item file
- **Output:** Clause Register

Cross-reference procedure:
1. Split the raw input into paragraphs/sentences
2. For each paragraph, verify at least one clause maps to it
3. For each clause, verify the text matches the original (no paraphrasing)
4. Flag any gaps (input content with no corresponding clause)

Report format:
```
## Step 1 Cross-Reference: Raw Input -> Clauses

| Raw Input Segment | Mapped Clause(s) | Status |
|-------------------|-------------------|--------|
| "Most rows show LangGraph..." | C1 [PROB] | COVERED |
| "The first 4 rows ALL say..." | C2 [FACT] | COVERED |
| ... | ... | ... |

Unmapped segments: 0
Total clauses: 9
```

#### Quality Gates

| Gate ID | Rule | Severity |
|---------|------|----------|
| QG-1.1 | Every paragraph/sentence in raw input has at least one clause | FAIL if violated |
| QG-1.2 | No clause reinterprets or paraphrases the original wording | WARN if violated |
| QG-1.3 | Ambiguous statements are flagged, not silently interpreted | WARN if violated |
| QG-1.4 | Each clause has exactly one type code | FAIL if violated |
| QG-1.5 | Clause IDs are sequential and unique (C1, C2, ... with no gaps) | FAIL if violated |
| QG-1.6 | Type summary counts match actual clause types | FAIL if violated |

---

### Step 2: 5 Whys Analysis

**Pipeline node:** intake_analyze (second phase)
**Artifact:** 5 Whys Analysis (five-whys.md)

#### Inputs
- Clause Register from Step 1

#### Process
Build a causal chain of 5 why-because pairs. Each pair must reference
specific C\<n\> clauses as evidence. Derive a Root Need statement.

#### Outputs
- 5 Why-Because pairs (W1..W5) with clause references
- Root Need statement referencing C-PROB and C-GOAL clauses
- W -> C traceability table

#### Validation Cross-Reference Report

The validator retrieves:
- **Input:** Clause Register
- **Output:** 5 Whys Analysis

Cross-reference procedure:
1. For each W\<n\>, verify referenced C\<n\> clauses exist in the register
2. Check causal chain coherence: does each W logically follow from the previous?
3. Check Root Need references C-PROB and C-GOAL clauses
4. Flag any W that introduces new information not present in any clause

Report format:
```
## Step 2 Cross-Reference: Clauses -> 5 Whys

| W<n> | Referenced Clauses | Clauses Exist? | New Info? | Coherent? |
|------|--------------------|----------------|-----------|-----------|
| W1 | C5 | YES | NO | -- (start) |
| W2 | C6, C7 | YES | NO | YES |
| W3 | C9 | YES | NO | YES |
| W4 | C8 | YES | NO | YES |
| W5 | (none) | -- | YES: flagged | YES |

Root Need references: C1 [PROB], C4 [GOAL] -- both exist: YES
New information flags: 1 (W5 introduces assumption, must be verified)
```

#### Quality Gates

| Gate ID | Rule | Severity |
|---------|------|----------|
| QG-2.1 | Every W references at least one C\<n\> | WARN if violated (flag as assumption) |
| QG-2.2 | All referenced C\<n\> IDs exist in the Clause Register | FAIL if violated |
| QG-2.3 | Causal chain is logically coherent (each W follows from previous) | WARN if violated |
| QG-2.4 | Root Need references at least one C-PROB and one C-GOAL clause | FAIL if violated |
| QG-2.5 | Any W introducing info not in any clause is flagged as assumption | FAIL if not flagged |
| QG-2.6 | Exactly 5 Whys are present (W1..W5) | WARN if fewer |

---

### Step 3: Structured Requirements

**Pipeline node:** structure_requirements (first phase)
**Artifact:** Structured Requirements (requirements.md)

#### Inputs
- Clause Register from Step 1
- 5 Whys Analysis from Step 2

#### Process
Transform clauses into typed requirements (UC/P/FR). Each requirement
references its source clauses. Produce a Clause Coverage Grid proving
every clause is mapped.

#### Outputs
- Requirements list: UC\<n\>, P\<n\>, FR\<n\> with source clause references
- Root causes reference W\<n\> from the 5 Whys
- Clause Coverage Grid: every C\<n\> mapped to UC/P/FR or marked unmapped with explanation

#### Validation Cross-Reference Report

The validator retrieves:
- **Input:** Clause Register, 5 Whys Analysis
- **Output:** Structured Requirements with Coverage Grid

Cross-reference procedure:
1. For each C\<n\> in the register, find it in the Coverage Grid
2. Verify every C\<n\> is either mapped to a requirement or has an unmapped explanation
3. For each requirement, verify source clause references point to real clauses
4. For each root cause, verify W\<n\> reference exists in the 5 Whys

Report format:
```
## Step 3 Cross-Reference: Clauses -> Requirements

| C<n> | Type | Mapped To | In Grid? | Status |
|------|------|-----------|----------|--------|
| C1 | PROB | UC1, P1 | YES | COVERED |
| C2 | FACT | P1 | YES | COVERED |
| ... | ... | ... | ... | ... |

Unmapped clauses: 0 (or list with explanations)
Requirements with broken clause refs: 0
Requirements with broken W<n> refs: 0
```

#### Quality Gates

| Gate ID | Rule | Severity |
|---------|------|----------|
| QG-3.1 | Every C\<n\> appears in the Coverage Grid | FAIL if missing |
| QG-3.2 | Every unmapped clause has an explicit justification | FAIL if missing |
| QG-3.3 | Every requirement has at least one source clause reference | FAIL if violated |
| QG-3.4 | All source clause references point to existing C\<n\> IDs | FAIL if violated |
| QG-3.5 | Root causes reference W\<n\> IDs that exist in the 5 Whys | FAIL if violated |
| QG-3.6 | Every C-PROB clause maps to at least one P\<n\> | FAIL if violated |
| QG-3.7 | Every C-GOAL clause maps to at least one UC\<n\> or FR\<n\> | FAIL if violated |

---

### Step 4: Acceptance Criteria Generation

**Pipeline node:** structure_requirements (second phase)
**Artifact:** AC Register (appended to requirements.md)

#### Inputs
- Clause Register from Step 1
- Structured Requirements from Step 3

#### Process
Generate numbered acceptance criteria. Each AC has an explicit origin
tracing back to a specific clause. The AC Register is the validation
contract -- the single source of truth for what "done" means.

#### AC Origin Rules

| Origin Type | Rule |
|-------------|------|
| Explicit (C-AC) | User-provided criterion preserved verbatim |
| Derived from C-PROB | Mechanical inverse: "X is broken" -> "Is X working? YES/NO" |
| Derived from C-GOAL | Made testable: "user should X" -> "Can user X? YES/NO" |

#### Outputs
- AC Register: AC\<n\> with statement, origin, belongs-to (UC/P/FR), source clauses
- Requirement -> AC coverage grid (every UC/P/FR has at least one AC)
- Clause -> AC coverage grid (showing which clauses are testable vs context)

#### Validation Cross-Reference Report

The validator retrieves:
- **Input:** Clause Register, Structured Requirements
- **Output:** AC Register with both coverage grids

Cross-reference procedure:
1. For each C-AC clause, verify it appears verbatim as an AC
2. For each C-PROB clause, verify at least one derived AC exists
3. For each C-GOAL clause, verify at least one derived AC exists
4. For each UC/P/FR, verify at least one AC belongs to it
5. For each AC, verify it belongs to a valid UC/P/FR
6. For C-FACT and C-CTX without ACs, verify explicit justification exists

Report format:
```
## Step 4 Cross-Reference: Clauses + Requirements -> ACs

### Clause -> AC Coverage
| C<n> | Type | AC<n> | How Derived | Status |
|------|------|-------|-------------|--------|
| C1 | PROB | AC1 | Inverse | COVERED |
| C4 | GOAL | AC2 | Made testable | COVERED |
| C5 | CTX | -- | Context, not testable | JUSTIFIED |
| ... | ... | ... | ... | ... |

### Requirement -> AC Coverage
| Requirement | ACs | Count | Status |
|-------------|-----|-------|--------|
| UC1 | AC2 | 1 | COVERED |
| P1 | AC1 | 1 | COVERED |
| ... | ... | ... | ... |

Orphaned ACs (not belonging to any requirement): 0
C-AC clauses missing verbatim ACs: 0
C-PROB clauses without derived ACs: 0
C-GOAL clauses without derived ACs: 0
Requirements without ACs: 0
```

#### Quality Gates

| Gate ID | Rule | Severity |
|---------|------|----------|
| QG-4.1 | Every C-AC clause appears verbatim as an AC | FAIL if violated |
| QG-4.2 | Every C-PROB has at least one derived AC | FAIL if violated |
| QG-4.3 | Every C-GOAL has at least one derived AC | FAIL if violated |
| QG-4.4 | Every UC/P/FR has at least one AC | FAIL if violated |
| QG-4.5 | No AC is orphaned (every AC belongs to a UC/P/FR) | WARN if violated |
| QG-4.6 | C-FACT and C-CTX without ACs have explicit justification | WARN if violated |
| QG-4.7 | AC statements are YES/NO verifiable questions | WARN if violated |

---

### Step 5: Design

**Pipeline node:** create_plan / planner agent
**Artifact:** Design Document (design.md)

#### Inputs
- Structured Requirements from Step 3
- AC Register from Step 4
- Codebase (read by the planner agent)

#### Process
Create design decisions addressing each requirement. Each D\<n\> specifies
which UC/P/FR it addresses and which AC\<n\> it contributes to satisfying.

#### Outputs
- Design decisions: D\<n\> with addresses (UC/P/FR), satisfies (AC), approach, files
- Design -> AC traceability grid

#### Validation Cross-Reference Report

The validator retrieves:
- **Input:** Structured Requirements, AC Register
- **Output:** Design Document

Cross-reference procedure:
1. For each UC/P/FR, verify at least one D\<n\> addresses it
2. For each AC\<n\>, verify it is reachable through at least one D\<n\>
3. For each D\<n\>, verify it addresses a valid UC/P/FR
4. Verify the Design -> AC traceability grid has no gaps

Report format:
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
| AC1 | D1 | Slug resolution | COVERED |
| AC2 | D1, D3 | Slug resolution + filter | COVERED |
| AC3 | D2 | DB backfill | COVERED |

Uncovered requirements: 0
Uncovered ACs: 0
Orphaned design decisions: 0
```

#### Quality Gates

| Gate ID | Rule | Severity |
|---------|------|----------|
| QG-5.1 | Every UC/P/FR has at least one D\<n\> | FAIL if violated |
| QG-5.2 | Every AC is reachable through at least one D\<n\> | FAIL if violated |
| QG-5.3 | No D\<n\> is orphaned (every D addresses a UC/P/FR) | WARN if violated |
| QG-5.4 | Design -> AC traceability grid is complete (no empty cells) | FAIL if violated |
| QG-5.5 | File paths in design decisions reference real files or clearly mark "(new)" | WARN if violated |

---

### Step 6: Implementation Plan

**Pipeline node:** create_plan / planner agent
**Artifact:** YAML Plan (plan.yaml)

#### Inputs
- Design Document from Step 5
- AC Register from Step 4

#### Process
Create YAML plan with tasks. Each task references which D\<n\> it implements
and which AC\<n\> it targets.

#### Outputs
- YAML plan with tasks: T\<n\> with D\<n\> reference, target ACs, agent assignment
- Task -> AC traceability grid
- AC coverage check (every AC targeted by at least one task)

#### Validation Cross-Reference Report

The validator retrieves:
- **Input:** Design Document, AC Register
- **Output:** YAML Plan

Cross-reference procedure:
1. For each D\<n\>, verify at least one task references it
2. For each AC\<n\>, verify at least one task targets it
3. For each task, verify its D\<n\> and AC\<n\> references are valid
4. Verify the Task -> AC traceability grid has no gaps

Report format:
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

Uncovered design decisions: 0
Uncovered ACs: 0
Tasks with invalid D<n> refs: 0
Tasks with invalid AC<n> refs: 0
```

#### Quality Gates

| Gate ID | Rule | Severity |
|---------|------|----------|
| QG-6.1 | Every D\<n\> has at least one task | FAIL if violated |
| QG-6.2 | Every AC is targeted by at least one task | FAIL if violated |
| QG-6.3 | No task references a D\<n\> that does not exist | FAIL if violated |
| QG-6.4 | No task references an AC\<n\> that does not exist | FAIL if violated |
| QG-6.5 | Task dependencies form a valid DAG (no cycles) | FAIL if violated |
| QG-6.6 | Each task has specific file paths | WARN if violated |

---

### Step 7: Per-Task Validation

**Pipeline node:** verify_fix (after each task)
**Artifact:** Task Validation Report (validation/task-{id}-{timestamp}.json)

#### Inputs
- AC Register from Step 4
- Task result (code changes, commits)
- Build/test commands

#### Process
After each task completes, the validator checks the ACs targeted by that task.
Only the ACs in that task's target_acs list are checked -- not the full register.

#### Outputs
- Per-AC findings: verdict (PASS/WARN/FAIL) with evidence
- Task-level verdict derived from per-AC findings
- requirements_checked and requirements_met counts

#### Validation Cross-Reference Report

The validator retrieves:
- **Input:** Task definition (including target_acs), AC Register
- **Output:** Task execution result (code changes)

Cross-reference procedure:
1. For each AC in the task's target_acs, run the appropriate verification
2. Record evidence for each AC (command output, file contents, page state)
3. Derive task verdict from individual AC verdicts

Report format:
```
## Step 7 Cross-Reference: Task T1.1 -> Target ACs

| AC<n> | Verdict | Evidence | Status |
|-------|---------|----------|--------|
| AC1 | PASS | 0 LangGraph rows on /proxy | CHECKED |
| AC2 | WARN | Filter works but 3 old traces unresolved | CHECKED |

Target ACs checked: 2/2
Task verdict: WARN (not 100%)
```

#### Quality Gates

| Gate ID | Rule | Severity |
|---------|------|----------|
| QG-7.1 | Every AC in the task's target_acs has a finding | FAIL if any skipped |
| QG-7.2 | Every finding has non-empty evidence | WARN if violated |
| QG-7.3 | Verdict follows rules: PASS = 100%, WARN = < 100%, FAIL = regression | FAIL if miscalculated |
| QG-7.4 | Build succeeds (no regressions from baseline) | FAIL if new build errors |
| QG-7.5 | Tests pass (no regressions from baseline) | FAIL if new test failures |

---

### Step 8: Final Item-Level Validation

**Pipeline node:** verify_fix (after ALL tasks complete)
**Artifact:** Final Validation Report (validation/final-{timestamp}.json) +
Full Traceability Matrix (traceability-matrix.md)

#### Inputs
- AC Register from Step 4 (ALL ACs, not just one task's targets)
- Current state of the system (live pages, DB, code)
- All per-task validation reports from Step 7

#### Process
After ALL tasks complete, run one final validation pass that checks EVERY
AC\<n\> against the current state. This is the archival gate. Also produce
the full end-to-end traceability matrix.

#### Outputs
- Final per-AC findings for every AC in the register
- Full Traceability Matrix: C -> UC/P/FR -> AC -> D -> T -> VF
- Final verdict (PASS/WARN/FAIL)

#### Validation Cross-Reference Report

The validator retrieves:
- **Input:** Clause Register, Requirements, AC Register, Design, Plan, Per-Task Reports
- **Output:** Current system state

Cross-reference procedure:
1. For EVERY AC\<n\> in the register, verify against current system state
2. Build full traceability matrix linking every clause to its final verdict
3. Check that no clause is orphaned at any level in the chain
4. Compare final findings against per-task findings for consistency

Report format:
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
| AC1 | PASS | 0 LangGraph rows on /proxy |
| AC2 | PASS | Filter returns correct results |
| AC3 | PASS | Backfilled traces show item_slug |

Total ACs: 3
Passed: 3
Final Verdict: PASS
```

#### Quality Gates

| Gate ID | Rule | Severity |
|---------|------|----------|
| QG-8.1 | EVERY AC\<n\> in the register has a finding (no skips) | FAIL if any missing |
| QG-8.2 | requirements_checked == total ACs in register | FAIL if mismatch |
| QG-8.3 | PASS only when requirements_met == requirements_checked | FAIL if miscalculated |
| QG-8.4 | Full traceability matrix covers every C\<n\> | FAIL if any orphaned |
| QG-8.5 | No clause is orphaned at any level (UC/P/FR, AC, D, T columns all filled) | WARN if gaps exist |
| QG-8.6 | Final findings consistent with per-task findings (no regressions) | WARN if inconsistent |

#### Archival Gate

| Final Verdict | Action |
|---------------|--------|
| PASS | Archive as COMPLETE |
| WARN | Hold for human review (do NOT archive as COMPLETE) |
| FAIL | Return to create_plan for retry |

---

## Validation Agent Skill Architecture

Each step's cross-reference and quality gate logic must be encoded as a
validator skill file so the validator agent can execute it mechanically.

### Skill File Map

| Skill File | Covers Steps | Purpose |
|------------|-------------|---------|
| clause-extraction-validation.md | Step 1 | Raw input -> Clause cross-ref + QG-1.x |
| five-whys-validation.md | Step 2 | Clauses -> 5 Whys cross-ref + QG-2.x |
| requirements-validation.md | Step 3 | Clauses -> Requirements cross-ref + QG-3.x |
| ac-generation-validation.md | Step 4 | Clauses + Reqs -> ACs cross-ref + QG-4.x |
| design-validation.md | Step 5 | Reqs + ACs -> Design cross-ref + QG-5.x |
| plan-validation.md | Step 6 | Design + ACs -> Tasks cross-ref + QG-6.x |
| task-validation.md | Step 7 | Task targets -> Findings cross-ref + QG-7.x (extends existing) |
| final-validation.md | Step 8 | Full traceability matrix + QG-8.x (extends existing) |

### Skill File Structure

Each skill file follows this structure:

```
# Validator Skill: {Step Name} (Step N)

## Inputs to Retrieve
- List of artifact files the validator must read before checking

## Cross-Reference Procedure
1. Numbered steps the validator follows mechanically
2. Each step specifies: what to compare, where to find it, what to look for

## Quality Gates
| Gate | Rule | How to Check | Severity |
...

## Report Format
The exact markdown/JSON format the validator must produce
```

### How the Validator Uses Skills

1. The pipeline invokes the validator after a step completes
2. The validator reads the relevant skill file for that step
3. The validator retrieves the input artifacts listed in the skill
4. The validator retrieves the output artifacts produced by the step
5. The validator executes the cross-reference procedure step by step
6. The validator evaluates each quality gate
7. The validator produces the report in the specified format
8. The verdict is derived from the quality gate results

### Integration with Existing Validator

The current validator (validator.md) handles Steps 7-8 via its existing skills:
- build-and-tests.md (build + unit tests)
- e2e-validation.md (Playwright + curl)
- requirements-check.md (P\<n\> requirements, placeholder scan, test data)
- code-review.md (coding standards)
- baseline-check.md (pre-existing failures)

The new skills for Steps 1-6 complement these. They validate the *analytical
artifacts* (clauses, requirements, ACs, design, plan) rather than the *code
artifacts* (builds, tests, pages). The existing skills remain unchanged for
Steps 7-8 code-level validation.

---

## Work Item Page: Complete Artifact View

The work item page displays all artifacts in order, giving the human a
complete audit trail:

1. **Raw Input** -- the original backlog item text
2. **Clause Register** -- C\<n\> with types and counts
3. **5 Whys Analysis** -- W\<n\> with clause references
4. **Structured Requirements** -- UC/P/FR with clause coverage grid
5. **AC Register** -- AC\<n\> with origins and coverage grids
6. **Design** -- D\<n\> with AC traceability
7. **Plan Tasks** -- T\<n\> with AC targets
8. **Per-Task Validation** -- findings by AC for each task
9. **Final Validation** -- full traceability matrix, final verdict
10. **Worker Output Logs** -- raw execution logs (collapsible)

This allows a human to:
- Verify nothing was lost from the raw input (clause coverage grid)
- Verify every requirement has acceptance criteria (AC coverage grid)
- Verify every AC was designed for (design -> AC grid)
- Verify every AC was implemented (task -> AC grid)
- Verify every AC was checked (final traceability matrix)
- Identify exactly where a failure occurred in the chain

---

## Quality Gate Summary

Total quality gates across all steps: 39

| Step | Gate Range | Count | Critical (FAIL) | Advisory (WARN) |
|------|-----------|-------|-----------------|-----------------|
| 1. Clause Extraction | QG-1.1 .. QG-1.6 | 6 | 4 | 2 |
| 2. 5 Whys | QG-2.1 .. QG-2.6 | 6 | 3 | 3 |
| 3. Requirements | QG-3.1 .. QG-3.7 | 7 | 7 | 0 |
| 4. AC Generation | QG-4.1 .. QG-4.7 | 7 | 3 | 4 |
| 5. Design | QG-5.1 .. QG-5.5 | 5 | 3 | 2 |
| 6. Plan | QG-6.1 .. QG-6.6 | 6 | 5 | 1 |
| 7. Per-Task | QG-7.1 .. QG-7.5 | 5 | 4 | 1 |
| 8. Final | QG-8.1 .. QG-8.6 | 6 | 4 | 2 |
| **Totals** | | **48** | **33** | **15** |
