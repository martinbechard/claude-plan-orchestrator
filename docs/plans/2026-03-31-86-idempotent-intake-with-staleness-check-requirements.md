# Structured Requirements: 86 Idempotent Intake With Staleness Check

Source: tmp/plans/.claimed/86-idempotent-intake-with-staleness-check.md
Generated: 2026-03-31T21:06:52.936748+00:00

## Requirements

### P1: Intake steps re-run from scratch on every restart
Type: performance
Priority: high
Source clauses: [C1, C2, C19, C20, C27]
Description: Pipeline intake steps (clause extraction, 5 Whys, requirements structuring) re-run from scratch on every restart, even when output artifacts already exist in the workspace. These steps call the Claude API and are expensive to repeat, wasting both API cost and time. The pipeline lacks any mechanism to check whether output artifacts already exist or validate whether they are still fresh relative to their inputs.
Acceptance Criteria:
- Does the pipeline skip intake steps whose output artifacts already exist and are still fresh? YES = pass, NO = fail
- Is API cost reduced when restarting a pipeline whose intake artifacts are already up to date? YES = pass, NO = fail

### P2: No baseline metadata for staleness comparison
Type: functional
Priority: high
Source clauses: [C22, C23]
Description: The system does not record metadata (hash or modification time) about the inputs at the time outputs are produced. Without this historical metadata, subsequent runs have no baseline to compare against, making it impossible to determine whether cached outputs are still valid.
Acceptance Criteria:
- Does the system record input metadata when producing output artifacts? YES = pass, NO = fail
- On restart, does the system have a baseline to compare current inputs against? YES = pass, NO = fail

### P3: _has_five_whys check is incomplete
Type: functional
Priority: medium
Source clauses: [C9, C24]
Description: The current _has_five_whys check only looks at the item file but does not check the workspace artifact (workspace/five-whys.md). This means the pipeline cannot correctly determine whether 5 Whys analysis has already been performed and is available in the workspace.
Acceptance Criteria:
- Does the 5 Whys freshness check examine the workspace artifact (workspace/five-whys.md) rather than only the item file? YES = pass, NO = fail

### FR1: Artifact existence check before each intake step
Type: functional
Priority: high
Source clauses: [C3, C4, C5, C6, C26]
Description: Before running each intake step, the system should check whether its output artifact already exists in the workspace. If it does, the system should compare the input's content hash (or modification time) against the output's modification time. If the output is newer than the input (i.e., still fresh), the step should be skipped and the existing artifact reused. If the input changed since the output was produced, the step must re-run.
Acceptance Criteria:
- Does each intake step check for an existing output artifact before running? YES = pass, NO = fail
- When the output is newer than the input, is the step skipped and the existing artifact reused? YES = pass, NO = fail
- When the input has changed since the output was produced, is the step re-run? YES = pass, NO = fail

### FR2: Staleness check for clause extraction
Type: functional
Priority: high
Source clauses: [C7]
Description: The clause extraction step should check workspace/clauses.md against the raw backlog item. If clauses.md exists and was produced from the current version of the backlog item, the step should be skipped.
Acceptance Criteria:
- Does clause extraction compare workspace/clauses.md freshness against the raw backlog item before running? YES = pass, NO = fail

### FR3: Staleness check for 5 Whys analysis
Type: functional
Priority: high
Source clauses: [C8]
Description: The 5 Whys step should check workspace/five-whys.md against the raw backlog item. If five-whys.md exists and was produced from the current version of the backlog item, the step should be skipped.
Acceptance Criteria:
- Does 5 Whys analysis compare workspace/five-whys.md freshness against the raw backlog item before running? YES = pass, NO = fail

### FR4: Staleness check for requirements structuring
Type: functional
Priority: high
Source clauses: [C10]
Description: The requirements structuring step should check the requirements doc against both clauses.md and five-whys.md. If the requirements doc exists and was produced from the current versions of both inputs, the step should be skipped.
Acceptance Criteria:
- Does requirements structuring compare the requirements doc freshness against both clauses.md and five-whys.md before running? YES = pass, NO = fail

### FR5: Staleness check for design creation
Type: functional
Priority: high
Source clauses: [C11]
Description: The design creation step should check the design doc against the requirements doc. If the design doc exists and was produced from the current version of the requirements doc, the step should be skipped.
Acceptance Criteria:
- Does design creation compare the design doc freshness against the requirements doc before running? YES = pass, NO = fail

### FR6: Staleness check for plan creation
Type: functional
Priority: high
Source clauses: [C12]
Description: The plan creation step should check the plan YAML against the design doc. If the plan YAML exists and was produced from the current version of the design doc, the step should be skipped.
Acceptance Criteria:
- Does plan creation compare the plan YAML freshness against the design doc before running? YES = pass, NO = fail

### FR7: Sidecar metadata file for input hash tracking
Type: functional
Priority: high
Source clauses: [C13, C14, C15, C16, C17, C25]
Description: For each step, the system should record the hash (or mtime) of the input(s) at the time the output is produced. This metadata should be stored as a sidecar file (e.g., workspace/.artifact-meta.json) mapping output filenames to their input hashes. On restart, the system should recompute the input hash and compare it against the stored value. If it matches, the output is still valid and the step is skipped. If it differs, the input changed and the step must re-run.
Acceptance Criteria:
- Is a sidecar metadata file (e.g., workspace/.artifact-meta.json) created/updated when output artifacts are produced? YES = pass, NO = fail
- Does the sidecar map each output filename to the hash(es) of its input(s)? YES = pass, NO = fail
- On restart, does the system recompute the input hash and compare it to the stored value? YES = pass, NO = fail
- When hashes match, is the output treated as valid and the step skipped? YES = pass, NO = fail
- When hashes differ, is the step re-run to regenerate the output? YES = pass, NO = fail

### FR8: Full pipeline idempotency
Type: non-functional
Priority: high
Source clauses: [C18, C21, C26]
Description: The entire pipeline should be idempotent: restarting a pipeline that has already completed intake steps should not re-run those steps unless their inputs have changed. Correctness must be maintained -- when a backlog item's content changes between runs, cached outputs that are now stale must be detected and regenerated, not reused incorrectly.
Acceptance Criteria:
- Is the full pipeline idempotent (restart produces the same result without redundant work)? YES = pass, NO = fail
- When inputs change between runs, are stale cached outputs correctly invalidated and regenerated? YES = pass, NO = fail
- Are no stale outputs ever reused when their inputs have changed? YES = pass, NO = fail

## Coverage Matrix
| Raw Input Section | Requirement(s) |
|---|---|
| "Pipeline intake ... re-runs from scratch on every restart" | P1 |
| "This wastes API cost and time" | P1 |
| "Before running each intake step, check whether its output artifact already exists" | FR1 |
| "compare the input's modification time (or content hash) against the output's modification time" | FR1 |
| "If the output is newer than the input, skip the step and reuse the existing artifact" | FR1 |
| "If the input changed since the output was produced, re-run the step" | FR1 |
| "Clause extraction: check workspace/clauses.md against the raw backlog item" | FR2 |
| "5 Whys: check workspace/five-whys.md against the raw backlog item" | FR3 |
| "_has_five_whys checks the item file but not the workspace" | P3 |
| "Requirements structuring: check requirements doc against clauses.md and five-whys.md" | FR4 |
| "Design creation: check design doc against requirements doc" | FR5 |
| "Plan creation: check plan YAML against design doc" | FR6 |
| "For each step, record the hash (or mtime) of the input(s) at the time the output was produced" | FR7 |
| "Store this as a sidecar (e.g. workspace/.artifact-meta.json)" | FR7 |
| "On restart, recompute the input hash and compare" | FR7 |
| "If it matches, the output is still valid" | FR7 |
| "If it differs, the input changed and the step must re-run" | FR7 |
| "This makes the entire pipeline idempotent without losing correctness" | FR8 |
| "The system doesn't record metadata ... about the inputs at the time outputs are produced" | P2 |
| "Without this historical metadata, subsequent runs have no baseline to compare against" | P2 |
| "the current _has_five_whys check only looks at the item file, not the workspace artifact" | P3 |
| "When a backlog item's content changes between runs, cached outputs become stale and incorrect" | FR8 |
| 5 Whys Root Need and Summary | P1, FR1, FR7, FR8 |

## Clause Coverage Grid
| Clause | Type | Mapped To | Status |
|---|---|---|---|
| C1 [FACT] | FACT | P1 | Mapped |
| C2 [PROB] | PROB | P1 | Mapped |
| C3 [AC] | AC | FR1 | Mapped |
| C4 [AC] | AC | FR1 | Mapped |
| C5 [AC] | AC | FR1 | Mapped |
| C6 [AC] | AC | FR1 | Mapped |
| C7 [AC] | AC | FR2 | Mapped |
| C8 [AC] | AC | FR3 | Mapped |
| C9 [FACT] | FACT | P3 | Mapped |
| C10 [AC] | AC | FR4 | Mapped |
| C11 [AC] | AC | FR5 | Mapped |
| C12 [AC] | AC | FR6 | Mapped |
| C13 [AC] | AC | FR7 | Mapped |
| C14 [AC] | AC | FR7 | Mapped |
| C15 [AC] | AC | FR7 | Mapped |
| C16 [AC] | AC | FR7 | Mapped |
| C17 [AC] | AC | FR7 | Mapped |
| C18 [GOAL] | GOAL | FR8 | Mapped |
| C19 [PROB] | PROB | P1 | Mapped |
| C20 [FACT] | FACT | P1 | Mapped |
| C21 [CONS] | CONS | FR8 | Mapped |
| C22 [FACT] | FACT | P2 | Mapped |
| C23 [FACT] | FACT | P2 | Mapped |
| C24 [FACT] | FACT | P3 | Mapped |
| C25 [GOAL] | GOAL | FR7 | Mapped |
| C26 [GOAL] | GOAL | FR1, FR8 | Mapped |
| C27 [PROB] | PROB | P1 | Mapped |

## Validation

Status: ACCEPTED
Iterations: 1
Reviewer notes: ACCEPT
