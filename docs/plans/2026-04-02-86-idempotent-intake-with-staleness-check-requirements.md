# Structured Requirements: 86 Idempotent Intake With Staleness Check

Source: tmp/plans/.claimed/86-idempotent-intake-with-staleness-check.md
Generated: 2026-04-02T18:39:24.223031+00:00

## Requirements

### P1: Redundant intake processing wastes API cost and time
Type: performance
Priority: high
Source clauses: [C1, C2, C19, C31]
Description: Pipeline intake steps (clause extraction, 5 Whys, requirements structuring) re-run from scratch on every restart, even when their output artifacts already exist in the workspace. The pipeline lacks any mechanism to check whether output artifacts already exist or validate whether they are still fresh relative to the input. Because these steps call the Claude API, redundant re-runs waste both API cost and wall-clock time.
Acceptance Criteria:
- Does the pipeline avoid re-running an intake step when its output artifact already exists and its inputs have not changed? YES = pass, NO = fail
- Is the total API cost reduced when restarting a pipeline whose artifacts are already up to date? YES = pass, NO = fail

### P2: Incomplete five-whys existence check
Type: functional
Priority: medium
Source clauses: [C9, C26]
Description: The current _has_five_whys helper only checks the backlog item file for embedded five-whys content. It does not check whether the workspace artifact (workspace/five-whys.md) exists. This means the pipeline cannot detect that a prior run already produced the five-whys output in the workspace, leading to unnecessary re-execution.
Acceptance Criteria:
- Does the five-whys existence check inspect the workspace artifact (workspace/five-whys.md) in addition to the item file? YES = pass, NO = fail

### P3: No input metadata recorded for staleness baseline
Type: functional
Priority: high
Source clauses: [C24, C25]
Description: The system does not record metadata (hash or modification time) about the inputs at the time outputs are produced. Without this historical metadata, subsequent runs have no baseline to compare against and cannot determine whether cached output is still valid or stale.
Acceptance Criteria:
- Does the system record input metadata (hash or mtime) at the time each output artifact is produced? YES = pass, NO = fail
- Can a subsequent run retrieve the recorded metadata for comparison? YES = pass, NO = fail

### FR1: Artifact existence and freshness check before each intake step
Type: functional
Priority: high
Source clauses: [C3, C4, C5, C6, C23]
Description: Before running each intake step, the system must check whether the step's output artifact already exists in the workspace. If it does, the system must compare the input's content hash (or modification time) against the recorded metadata for that output. If the output is still fresh (input hash matches), the step is skipped and the existing artifact is reused. If the input changed since the output was produced, the step must re-run to regenerate the artifact.
Acceptance Criteria:
- Does each intake step check for the existence of its output artifact before executing? YES = pass, NO = fail
- When the output exists and inputs have not changed, is the step skipped? YES = pass, NO = fail
- When the output exists but inputs have changed, is the step re-run? YES = pass, NO = fail

### FR2: Sidecar metadata file for input hashes
Type: functional
Priority: high
Source clauses: [C13, C14, C29]
Description: For each step, the system must record the hash (or mtime) of the input(s) at the time the output is produced. This metadata must be stored as a sidecar file (e.g. workspace/.artifact-meta.json) that maps output filenames to their input hashes. This sidecar approach is the preferred staleness mechanism.
Acceptance Criteria:
- Does a sidecar metadata file (e.g. workspace/.artifact-meta.json) exist after an intake step produces output? YES = pass, NO = fail
- Does the sidecar file map each output filename to the hash(es) of its input(s) at production time? YES = pass, NO = fail
- Is the sidecar file updated each time an output artifact is regenerated? YES = pass, NO = fail

### FR3: Hash recomputation and comparison on restart
Type: functional
Priority: high
Source clauses: [C15, C16, C17, C27]
Description: On pipeline restart, the system must recompute the content hash of each step's input(s) and compare it against the hash stored in the sidecar metadata file. If the hashes match, the output is still valid and the step is skipped. If the hashes differ, the input has changed and the step must re-run. This mechanism allows the pipeline to automatically determine whether cached output is still valid or must be regenerated.
Acceptance Criteria:
- Does the system recompute input hashes on restart? YES = pass, NO = fail
- When the recomputed hash matches the stored hash, is the step skipped? YES = pass, NO = fail
- When the recomputed hash differs from the stored hash, is the step re-run? YES = pass, NO = fail

### FR4: Clause extraction staleness check
Type: functional
Priority: high
Source clauses: [C7]
Description: The clause extraction step must check workspace/clauses.md against the raw backlog item. If clauses.md exists and the backlog item has not changed since it was produced, clause extraction is skipped.
Acceptance Criteria:
- Does clause extraction check workspace/clauses.md against the raw backlog item before running? YES = pass, NO = fail
- Is clause extraction skipped when clauses.md is fresh? YES = pass, NO = fail

### FR5: Five-Whys staleness check
Type: functional
Priority: high
Source clauses: [C8]
Description: The 5 Whys step must check workspace/five-whys.md against the raw backlog item. If five-whys.md exists and the backlog item has not changed since it was produced, the 5 Whys step is skipped.
Acceptance Criteria:
- Does the 5 Whys step check workspace/five-whys.md against the raw backlog item before running? YES = pass, NO = fail
- Is the 5 Whys step skipped when five-whys.md is fresh? YES = pass, NO = fail

### FR6: Requirements structuring staleness check
Type: functional
Priority: high
Source clauses: [C10]
Description: The requirements structuring step must check its output requirements document against both clauses.md and five-whys.md. If the requirements doc exists and neither input has changed since it was produced, the step is skipped.
Acceptance Criteria:
- Does requirements structuring check its output against both clauses.md and five-whys.md? YES = pass, NO = fail
- Is requirements structuring skipped when both inputs are unchanged? YES = pass, NO = fail
- Is requirements structuring re-run when either input has changed? YES = pass, NO = fail

### FR7: Design creation staleness check
Type: functional
Priority: high
Source clauses: [C11]
Description: The design creation step must check its output design document against the requirements document. If the design doc exists and the requirements doc has not changed since it was produced, the step is skipped.
Acceptance Criteria:
- Does design creation check its output against the requirements document? YES = pass, NO = fail
- Is design creation skipped when the requirements doc is unchanged? YES = pass, NO = fail

### FR8: Plan creation staleness check
Type: functional
Priority: high
Source clauses: [C12]
Description: The plan creation step must check the output plan YAML against the design document. If the plan YAML exists and the design doc has not changed since it was produced, the step is skipped.
Acceptance Criteria:
- Does plan creation check the plan YAML against the design document? YES = pass, NO = fail
- Is plan creation skipped when the design doc is unchanged? YES = pass, NO = fail

### FR9: End-to-end pipeline idempotency with correctness
Type: non-functional
Priority: high
Source clauses: [C18, C22, C28, C30]
Description: The entire pipeline must be idempotent: restarting it with unchanged inputs must produce the same result without re-running completed steps. When a backlog item's content changes between runs, cached outputs that depend on the changed input must be detected as stale and regenerated. The system must eliminate redundant API calls while maintaining output correctness -- no stale artifacts may be served when inputs have changed.
Acceptance Criteria:
- Does restarting the pipeline with unchanged inputs skip all previously completed steps? YES = pass, NO = fail
- Does modifying a backlog item cause all downstream steps to re-run? YES = pass, NO = fail
- Are final outputs identical whether the pipeline ran uninterrupted or was restarted mid-way (with unchanged inputs)? YES = pass, NO = fail

---

## Coverage Matrix
| Raw Input Section | Requirement(s) |
|---|---|
| "Pipeline intake...re-runs from scratch on every restart, even when output artifacts already exist" | P1 |
| "This wastes API cost and time" | P1 |
| "Before running each intake step, check whether its output artifact already exists" | FR1 |
| "compare the input's modification time (or content hash) against the output's modification time" | FR1 |
| "If the output is newer than the input, skip the step and reuse the existing artifact" | FR1 |
| "If the input changed since the output was produced, re-run the step" | FR1 |
| "Clause extraction: check workspace/clauses.md against the raw backlog item" | FR4 |
| "5 Whys: check workspace/five-whys.md against the raw backlog item" | FR5 |
| "_has_five_whys checks the item file but not the workspace" | P2 |
| "Requirements structuring: check requirements doc against clauses.md and five-whys.md" | FR6 |
| "Design creation: check design doc against requirements doc" | FR7 |
| "Plan creation: check plan YAML against design doc" | FR8 |
| "For each step, record the hash (or mtime) of the input(s) at the time the output was produced" | FR2 |
| "Store this as a sidecar (e.g. workspace/.artifact-meta.json) mapping output filenames to their input hashes" | FR2 |
| "On restart, recompute the input hash and compare" | FR3 |
| "If it matches, the output is still valid" | FR3 |
| "If it differs, the input changed and the step must re-run" | FR3 |
| "This makes the entire pipeline idempotent without losing correctness" | FR9 |
| 5 Whys W1: pipeline lacks mechanism to check output artifacts | P1 |
| 5 Whys W2: re-running steps wastes API cost and time | P1 |
| 5 Whys W3: cached outputs become stale when input changes | FR9 |
| 5 Whys W4: system doesn't record input metadata | P3 |
| 5 Whys W4: _has_five_whys only checks item file, not workspace | P2 |
| 5 Whys W5: recording input hashes enables automatic validity determination | FR3 |
| Root Need: idempotent intake mechanism with metadata comparison | FR9 |

## Clause Coverage Grid
| Clause | Type | Mapped To | Status |
|---|---|---|---|
| C1 | FACT | P1 | Mapped |
| C2 | PROB | P1 | Mapped |
| C3 | GOAL | FR1 | Mapped |
| C4 | GOAL | FR1 | Mapped |
| C5 | AC | FR1 | Mapped |
| C6 | AC | FR1 | Mapped |
| C7 | GOAL | FR4 | Mapped |
| C8 | GOAL | FR5 | Mapped |
| C9 | FACT | P2 | Mapped |
| C10 | GOAL | FR6 | Mapped |
| C11 | GOAL | FR7 | Mapped |
| C12 | GOAL | FR8 | Mapped |
| C13 | GOAL | FR2 | Mapped |
| C14 | GOAL | FR2 | Mapped |
| C15 | GOAL | FR3 | Mapped |
| C16 | AC | FR3 | Mapped |
| C17 | AC | FR3 | Mapped |
| C18 | GOAL | FR9 | Mapped |
| C19 | PROB | P1 | Mapped |
| C20 | CTX | P1 | Mapped |
| C21 | CTX | P1 | Mapped |
| C22 | FACT | FR9 | Mapped |
| C23 | GOAL | FR1 | Mapped |
| C24 | FACT | P3 | Mapped |
| C25 | FACT | P3 | Mapped |
| C26 | FACT | P2 | Mapped |
| C27 | GOAL | FR3 | Mapped |
| C28 | GOAL | FR9 | Mapped |
| C29 | CTX | FR2 | Mapped |
| C30 | GOAL | FR9 | Mapped |
| C31 | PROB | P1 | Mapped |

## Validation

Status: ACCEPTED
Iterations: 1
Reviewer notes: ACCEPT


## Acceptance Criteria

**Explicit (verbatim from C-AC clauses):**

**AC1:** If the output artifact is newer than (fresher than) the input, is the step skipped and the existing artifact reused? YES = pass, NO = fail
  Origin: Explicit from C5 [AC]
  Belongs to: FR1
  Source clauses: [C5]

**AC2:** If the input changed since the output was produced, is the step re-run? YES = pass, NO = fail
  Origin: Explicit from C6 [AC]
  Belongs to: FR1
  Source clauses: [C6]

**AC3:** If the recomputed input hash matches the stored hash, is the output treated as still valid and the step skipped? YES = pass, NO = fail
  Origin: Explicit from C16 [AC]
  Belongs to: FR3
  Source clauses: [C16]

**AC4:** If the recomputed input hash differs from the stored hash, is the step re-run? YES = pass, NO = fail
  Origin: Explicit from C17 [AC]
  Belongs to: FR3
  Source clauses: [C17]

---

**Derived from C-PROB clauses (inverted):**

**AC5:** Is API cost and wall-clock time reduced when restarting a pipeline whose output artifacts are already up to date? YES = pass, NO = fail
  Origin: Derived from C2 [PROB] (inverse) and C31 [PROB] (inverse)
  Belongs to: P1
  Source clauses: [C2, C31]

**AC6:** Does the pipeline check whether output artifacts already exist in the workspace and validate their freshness before running each intake step? YES = pass, NO = fail
  Origin: Derived from C19 [PROB] (inverse)
  Belongs to: P1
  Source clauses: [C19]

---

**Derived from C-GOAL clauses (operationalized):**

**AC7:** Before running each intake step, does the system check whether its output artifact already exists in the workspace? YES = pass, NO = fail
  Origin: Derived from C3 [GOAL] (operationalized)
  Belongs to: FR1
  Source clauses: [C3]

**AC8:** When an output artifact exists, does the system compare the input's content hash (or mtime) against the recorded metadata for that output? YES = pass, NO = fail
  Origin: Derived from C4 [GOAL] (operationalized)
  Belongs to: FR1
  Source clauses: [C4]

**AC9:** Does the pipeline detect input changes and invalidate cached outputs accordingly? YES = pass, NO = fail
  Origin: Derived from C23 [GOAL] (operationalized)
  Belongs to: FR1
  Source clauses: [C23]

**AC10:** Does clause extraction check workspace/clauses.md against the raw backlog item before running, and skip when clauses.md is fresh? YES = pass, NO = fail
  Origin: Derived from C7 [GOAL] (operationalized)
  Belongs to: FR4
  Source clauses: [C7]

**AC11:** Does the 5 Whys step check workspace/five-whys.md against the raw backlog item before running, and skip when five-whys.md is fresh? YES = pass, NO = fail
  Origin: Derived from C8 [GOAL] (operationalized)
  Belongs to: FR5
  Source clauses: [C8]

**AC12:** Does requirements structuring check its output against both clauses.md and five-whys.md, and re-run when either input has changed? YES = pass, NO = fail
  Origin: Derived from C10 [GOAL] (operationalized)
  Belongs to: FR6
  Source clauses: [C10]

**AC13:** Does design creation check its output design document against the requirements document, and skip when the requirements doc is unchanged? YES = pass, NO = fail
  Origin: Derived from C11 [GOAL] (operationalized)
  Belongs to: FR7
  Source clauses: [C11]

**AC14:** Does plan creation check the plan YAML against the design document, and skip when the design doc is unchanged? YES = pass, NO = fail
  Origin: Derived from C12 [GOAL] (operationalized)
  Belongs to: FR8
  Source clauses: [C12]

**AC15:** Does the system record the content hash of each step's input(s) at the time the output is produced? YES = pass, NO = fail
  Origin: Derived from C13 [GOAL] (operationalized)
  Belongs to: FR2
  Source clauses: [C13]

**AC16:** Is the input metadata stored in a sidecar file (workspace/.artifact-meta.json) that maps output filenames to their input hashes? YES = pass, NO = fail
  Origin: Derived from C14 [GOAL] (operationalized)
  Belongs to: FR2
  Source clauses: [C14]

**AC17:** On pipeline restart, does the system recompute the content hash of each step's input(s) and compare against the stored hash? YES = pass, NO = fail
  Origin: Derived from C15 [GOAL] (operationalized)
  Belongs to: FR3
  Source clauses: [C15]

**AC18:** Can the system automatically determine whether cached output is valid or must be regenerated by comparing recorded and recomputed input hashes? YES = pass, NO = fail
  Origin: Derived from C27 [GOAL] (operationalized)
  Belongs to: FR3
  Source clauses: [C27]

**AC19:** Does restarting the pipeline with unchanged inputs produce the same result without re-running completed steps? YES = pass, NO = fail
  Origin: Derived from C18 [GOAL] (operationalized)
  Belongs to: FR9
  Source clauses: [C18]

**AC20:** Are redundant API calls eliminated while maintaining output correctness (no stale artifacts served when inputs have changed)? YES = pass, NO = fail
  Origin: Derived from C28 [GOAL] (operationalized)
  Belongs to: FR9
  Source clauses: [C28]

**AC21:** Does the pipeline implement an idempotent intake mechanism that caches output artifacts, skips steps when outputs are fresh, and re-runs steps when inputs change, using input/output metadata comparison? YES = pass, NO = fail
  Origin: Derived from C30 [GOAL] (operationalized)
  Belongs to: FR9
  Source clauses: [C30]

**AC22:** When a backlog item's content changes between runs, are all downstream cached outputs detected as stale and regenerated? YES = pass, NO = fail
  Origin: Derived from C22 [FACT] (made testable -- consequence of staleness detection)
  Belongs to: FR9
  Source clauses: [C22]

---

**Derived for P2 and P3:**

**AC23:** Does the five-whys existence check inspect the workspace artifact (workspace/five-whys.md) in addition to the item file? YES = pass, NO = fail
  Origin: Derived from C9 [FACT] and C26 [FACT] (inverse of current gap)
  Belongs to: P2
  Source clauses: [C9, C26]

**AC24:** Does the system record input metadata (hash or mtime) at the time each output artifact is produced? YES = pass, NO = fail
  Origin: Derived from C24 [FACT] (inverse of current gap)
  Belongs to: P3
  Source clauses: [C24]

**AC25:** Can a subsequent pipeline run retrieve the previously recorded input metadata for comparison? YES = pass, NO = fail
  Origin: Derived from C25 [FACT] (inverse of current gap)
  Belongs to: P3
  Source clauses: [C25]

---

## Requirement -> AC Coverage

| Requirement | ACs | Count |
|---|---|---|
| P1 | AC5, AC6 | 2 |
| P2 | AC23 | 1 |
| P3 | AC24, AC25 | 2 |
| FR1 | AC1, AC2, AC7, AC8, AC9 | 5 |
| FR2 | AC15, AC16 | 2 |
| FR3 | AC3, AC4, AC17, AC18 | 4 |
| FR4 | AC10 | 1 |
| FR5 | AC11 | 1 |
| FR6 | AC12 | 1 |
| FR7 | AC13 | 1 |
| FR8 | AC14 | 1 |
| FR9 | AC19, AC20, AC21, AC22 | 4 |

## Clause -> AC Coverage

| Clause | Type | AC | How |
|---|---|---|---|
| C1 | FACT | -- | Context: describes current behavior; tested indirectly via P1 ACs (AC5, AC6) which verify the fix |
| C2 | PROB | AC5 | Inverse |
| C3 | GOAL | AC7 | Operationalized |
| C4 | GOAL | AC8 | Operationalized |
| C5 | AC | AC1 | Verbatim |
| C6 | AC | AC2 | Verbatim |
| C7 | GOAL | AC10 | Operationalized |
| C8 | GOAL | AC11 | Operationalized |
| C9 | FACT | AC23 | Inverse of gap |
| C10 | GOAL | AC12 | Operationalized |
| C11 | GOAL | AC13 | Operationalized |
| C12 | GOAL | AC14 | Operationalized |
| C13 | GOAL | AC15 | Operationalized |
| C14 | GOAL | AC16 | Operationalized |
| C15 | GOAL | AC17 | Operationalized |
| C16 | AC | AC3 | Verbatim |
| C17 | AC | AC4 | Verbatim |
| C18 | GOAL | AC19 | Operationalized |
| C19 | PROB | AC6 | Inverse |
| C20 | CTX | -- | Context: explains why redundant re-runs matter (cost); not independently testable; covered by P1 ACs |
| C21 | CTX | -- | Context: explains expense of API calls; motivates P1; not independently testable |
| C22 | FACT | AC22 | Made testable (staleness cascade) |
| C23 | GOAL | AC9 | Operationalized |
| C24 | FACT | AC24 | Inverse of gap |
| C25 | FACT | AC25 | Inverse of gap |
| C26 | FACT | AC23 | Inverse of gap |
| C27 | GOAL | AC18 | Operationalized |
| C28 | GOAL | AC20 | Operationalized |
| C29 | CTX | -- | Context: states sidecar is the preferred mechanism; design constraint tested indirectly via AC16 (verifies sidecar file exists) |
| C30 | GOAL | AC21 | Operationalized |
| C31 | PROB | AC5 | Inverse |
