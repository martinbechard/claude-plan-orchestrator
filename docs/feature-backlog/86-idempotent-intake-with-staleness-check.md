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
