# Idempotent intake: skip completed steps unless inputs changed

Pipeline intake (clause extraction, 5 Whys, requirements structuring) re-runs from scratch on every restart, even when output artifacts already exist in the workspace. This wastes API cost and time.

## Expected behavior

Before running each intake step, check whether its output artifact already exists in the workspace. If it does, compare the input's modification time (or content hash) against the output's modification time. If the output is newer than the input, skip the step and reuse the existing artifact. If the input changed since the output was produced, re-run the step.

## Steps affected

- Clause extraction: check workspace/clauses.md against the raw backlog item
- 5 Whys: check workspace/five-whys.md against the raw backlog item (partially done -- _has_five_whys checks the item file but not the workspace)
- Requirements structuring: check requirements doc against clauses.md and five-whys.md
- Design creation: check design doc against requirements doc
- Plan creation: check plan YAML against design doc

## Staleness detection approach

For each step, record the hash (or mtime) of the input(s) at the time the output was produced. Store this as a sidecar (e.g. workspace/.artifact-meta.json) mapping output filenames to their input hashes. On restart, recompute the input hash and compare. If it matches, the output is still valid. If it differs, the input changed and the step must re-run.

This makes the entire pipeline idempotent without losing correctness when inputs are modified between runs.

## LangSmith Trace: d16919cb-84cc-4abf-9e40-1b3bbaf11526


## 5 Whys Analysis

Title: Idempotent intake with staleness detection

Clarity: 4

5 Whys:

W1: Why do intake steps re-run from scratch on every restart?
    Because: The pipeline lacks any mechanism to check whether output artifacts already exist in the workspace or validate whether they're still fresh relative to the input (C1, C3).

W2: Why is reusing existing artifacts important?
    Because: Re-running intake steps (clause extraction, 5 Whys, requirements structuring) that already produced outputs wastes API cost and time, since these steps call Claude API and are expensive to repeat (C2, C7, C8, C10).

W3: Why can't the pipeline just cache all artifacts indefinitely?
    Because: When a backlog item's content changes between runs, cached outputs become stale and incorrect (C5, C6). The pipeline must detect input changes to know when to invalidate the cache and re-run the step.

W4: Why doesn't the pipeline currently detect when inputs have changed?
    Because: The system doesn't record metadata (hash or modification time) about the inputs at the time outputs are produced (C13, C14). Without this historical metadata, subsequent runs have no baseline to compare against, and the current _has_five_whys check only looks at the item file, not the workspace artifact (C9).

W5: Why is storing input metadata in a sidecar file the right approach?
    Because: By recording input hashes when outputs are created, then recomputing and comparing hashes on restart, the pipeline can automatically determine if cached output is still valid or must be regenerated (C15, C16, C17). This approach eliminates redundant API calls while maintaining output correctness [ASSUMPTION: sidecar metadata is preferred over other staleness mechanisms].

Root Need: The pipeline requires an idempotent intake mechanism that caches output artifacts and automatically skips processing steps when their outputs remain fresh, but re-runs steps whenever their inputs change, using input/output metadata comparison to determine staleness (C1, C2, C3, C4, C6, C13, C14, C18).

Summary: The pipeline wastes API cost on redundant intake steps because it lacks a staleness-detection mechanism based on input/output metadata tracking.
