# Design: 86 Idempotent Intake With Staleness Check

Source: tmp/plans/.claimed/86-idempotent-intake-with-staleness-check.md
Requirements: docs/plans/2026-04-02-86-idempotent-intake-with-staleness-check-requirements.md

## Architecture Overview

The pipeline intake flow (clause extraction -> 5 Whys -> requirements structuring ->
design creation -> plan creation) currently re-runs all steps from scratch on every
restart. This design adds a sidecar-metadata-based caching layer that records input
content hashes when outputs are produced, then compares them on restart to skip
steps whose outputs are still fresh.

The approach mirrors make-style dependency tracking: each step declares its inputs
and output, a sidecar JSON file records the input hashes at output-production time,
and a freshness check recomputes hashes before each step to decide skip-vs-rerun.

### Key files

New:
- langgraph_pipeline/shared/artifact_cache.py -- core cache module
- tests/langgraph/shared/test_artifact_cache.py -- unit tests for cache module

Modified:
- langgraph_pipeline/pipeline/nodes/intake.py -- add freshness checks to clause extraction, 5 Whys
- langgraph_pipeline/pipeline/nodes/requirements.py -- add freshness check to requirements structuring
- langgraph_pipeline/pipeline/nodes/plan_creation.py -- add freshness check to design/plan creation
- tests/langgraph/pipeline/nodes/test_intake.py -- tests for intake idempotency
- tests/langgraph/pipeline/nodes/test_requirements.py -- tests for requirements idempotency
- tests/langgraph/pipeline/nodes/test_plan_creation.py -- tests for plan creation idempotency

## Design Decisions

### D1: Sidecar metadata module with SHA-256 content hashing

Addresses: P3, FR2, FR3
Satisfies: AC3, AC4, AC15, AC16, AC17, AC18, AC24, AC25
Approach: Create a new module langgraph_pipeline/shared/artifact_cache.py with two
main functions:

- record_artifact(workspace_dir, output_name, input_paths) -- reads each input file,
  computes its SHA-256 content hash, and writes/updates the sidecar file
  workspace/.artifact-meta.json with an entry mapping output_name to a dict of
  {input_path: hash} pairs and a timestamp.

- is_artifact_fresh(workspace_dir, output_name, input_paths) -- checks that (a) the
  output file exists in the workspace, (b) the sidecar file has an entry for
  output_name, and (c) the current SHA-256 hashes of all input_paths match the
  stored hashes. Returns True only if all three conditions hold.

Content hashing (SHA-256) is chosen over mtime because it is immune to filesystem
clock skew and backup/restore operations that preserve mtime but change content.

The sidecar file path is workspace/.artifact-meta.json (one per item workspace).

Files: langgraph_pipeline/shared/artifact_cache.py (new),
       tests/langgraph/shared/test_artifact_cache.py (new)


### D2: Clause extraction freshness check

Addresses: P1, FR1, FR4
Satisfies: AC1, AC2, AC5, AC6, AC7, AC8, AC9, AC10
Approach: In _run_intake_analysis(), before calling _run_clause_extraction(), check
is_artifact_fresh(workspace, "clauses.md", [item_path]). If fresh, load the existing
clauses.md content and skip the LLM call + validation. After producing new clauses,
call record_artifact() to update the sidecar.

Files: langgraph_pipeline/pipeline/nodes/intake.py


### D3: Five-Whys freshness check and workspace artifact detection

Addresses: P1, P2, FR1, FR5
Satisfies: AC1, AC2, AC5, AC6, AC7, AC8, AC9, AC11, AC23
Approach: Replace the LLM-based _has_five_whys(item_path) check with a file-based
freshness check: is_artifact_fresh(workspace, "five-whys.md", [item_path]). This
addresses P2 (the check now inspects workspace/five-whys.md) and eliminates the
wasteful Haiku LLM call. After producing new five-whys output, call record_artifact().

The existing _has_five_whys() function is retained as a fallback only when the
workspace sidecar has no entry (first run after migration), but its result is no
longer the primary gate.

Files: langgraph_pipeline/pipeline/nodes/intake.py


### D4: Requirements structuring freshness check

Addresses: FR1, FR6
Satisfies: AC1, AC2, AC7, AC8, AC9, AC12
Approach: In structure_requirements(), after the existing plan_path/requirements_path
short-circuits, add a freshness check: is_artifact_fresh(workspace, "requirements.md",
[clause_register_path, five_whys_path]). If fresh and the docs/plans/ requirements
file also exists, skip the step. After producing new requirements, call
record_artifact(). The input_paths list includes both clauses.md and five-whys.md
from the workspace, matching FR6's multi-input staleness requirement.

Files: langgraph_pipeline/pipeline/nodes/requirements.py


### D5: Design and plan creation freshness checks

Addresses: FR1, FR7, FR8
Satisfies: AC1, AC2, AC7, AC8, AC9, AC13, AC14
Approach: In create_plan(), before spawning Claude, check freshness of the design
doc against the requirements doc: is_artifact_fresh(workspace, "design.md",
[requirements_path]). Similarly check plan YAML freshness against the design doc:
is_artifact_fresh(workspace, "plan.yaml", [design_doc_path]). If both are fresh
and the actual files exist at their expected paths, skip the entire create_plan step.
After producing new design/plan, call record_artifact() for each.

Since create_plan spawns Claude as a subprocess that produces both files atomically,
the freshness check gates the entire step. If the design is stale but the plan is
not (unlikely but possible if plan was manually edited), the step re-runs fully.

Files: langgraph_pipeline/pipeline/nodes/plan_creation.py


### D6: Cascade invalidation via hash propagation

Addresses: FR9
Satisfies: AC19, AC20, AC21, AC22
Approach: No explicit cascade logic is needed. Because each step checks its own
inputs' current hashes, a change to the backlog item automatically invalidates
clauses.md (different hash), which causes clauses to be regenerated. The new
clauses.md has a different hash than what the requirements step recorded, so
requirements re-run too. This cascading effect propagates naturally through the
chain: item -> clauses -> five-whys -> requirements -> design -> plan.

The is_artifact_fresh() function handles the cascade implicitly: if any input file
was regenerated (and thus has a new hash), all downstream steps detect staleness.

Files: No additional files -- this is an emergent property of D1-D5.


## Design -> AC Traceability Grid

| AC | Design Decision(s) | Approach |
|---|---|---|
| AC1 | D2, D3, D4, D5 | Each step checks freshness; fresh outputs are skipped |
| AC2 | D2, D3, D4, D5 | Changed inputs cause hash mismatch -> step re-runs |
| AC3 | D1 | is_artifact_fresh returns True when hashes match -> skip |
| AC4 | D1 | is_artifact_fresh returns False when hashes differ -> re-run |
| AC5 | D2, D3, D4, D5 | Skipping steps avoids LLM calls -> reduced API cost |
| AC6 | D2, D3, D4, D5 | Each intake step checks output existence + freshness |
| AC7 | D2, D3, D4, D5 | Output existence check is first gate in is_artifact_fresh |
| AC8 | D2, D3, D4, D5 | Hash comparison against sidecar metadata |
| AC9 | D2, D3, D4, D5 | Hash mismatch triggers invalidation |
| AC10 | D2 | Clause extraction checks clauses.md vs item_path |
| AC11 | D3 | 5 Whys checks five-whys.md vs item_path |
| AC12 | D4 | Requirements checks against clauses.md + five-whys.md |
| AC13 | D5 | Design checks against requirements doc |
| AC14 | D5 | Plan checks against design doc |
| AC15 | D1 | record_artifact stores SHA-256 hashes at production time |
| AC16 | D1 | Sidecar .artifact-meta.json maps output -> input hashes |
| AC17 | D1 | is_artifact_fresh recomputes hashes on restart |
| AC18 | D1 | Comparison of stored vs recomputed hashes determines validity |
| AC19 | D6 | Unchanged inputs -> all hashes match -> all steps skipped |
| AC20 | D6 | Stale artifacts detected via hash mismatch -> re-run |
| AC21 | D1, D6 | Full pipeline idempotency via sidecar metadata comparison |
| AC22 | D6 | Hash cascade: changed item -> stale clauses -> stale downstream |
| AC23 | D3 | Freshness check inspects workspace/five-whys.md directly |
| AC24 | D1 | record_artifact records input hashes at output production time |
| AC25 | D1 | is_artifact_fresh retrieves stored hashes for comparison |
