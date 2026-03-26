# Design: Move task-status.json Outside .claude/ Directory

## Problem

Claude Code's sensitive file protection blocks all writes to paths under `.claude/`,
even when running with `--dangerously-skip-permissions`. Workers trying to write
`.claude/plans/task-status.json` receive 6 consecutive permission denials and give up,
leaving the executor with no task outcome to read.

## Solution

Move `task-status.json` from `.claude/plans/task-status.json` to `tmp/task-status.json`
(project root). The `tmp/` path is outside `.claude/` and will not be protected by
Claude Code's sensitive file policy.

This is Fix Option 1 from the backlog item: relocate the file outside `.claude/`.

## Key Files to Modify

### Path constant

- `langgraph_pipeline/shared/paths.py` — change `STATUS_FILE_PATH` from
  `.claude/plans/task-status.json` to `tmp/task-status.json`

### Parallel executor constant

- `langgraph_pipeline/executor/nodes/parallel.py` — change
  `WORKTREE_STATUS_FILE_RELATIVE` from `.claude/plans/task-status.json` to
  `tmp/task-status.json`; this is the worktree-relative path agents write to and
  the parallel executor reads from

### Agent markdown files (write path instructions)

All agent definitions that instruct Claude to write `task-status.json` must be updated:

- `.claude/agents/coder.md`
- `.claude/agents/validator.md`
- `.claude/agents/frontend-coder.md`
- `.claude/agents/code-reviewer.md`
- `.claude/agents/planner.md`
- `.claude/agents/issue-verifier.md`
- `.claude/agents/qa-auditor.md`
- `.claude/agents/ux-reviewer.md`
- `.claude/agents/e2e-analyzer.md`
- `.claude/agents/systems-designer.md`
- `.claude/agents/spec-verifier.md`
- `.claude/agents/ux-designer.md`

### Gitignore

- `.gitignore` — update the existing `.claude/plans/task-status.json` entry to
  `tmp/task-status.json`

### Tests

- `tests/langgraph/shared/test_paths.py` — update path assertion
- Other test files that hardcode `.claude/plans/task-status.json` — update path string

## Design Decisions

1. **`tmp/` over project root**: Using `tmp/task-status.json` rather than
   `task-status.json` at the project root keeps ephemeral files organized and avoids
   cluttering the root directory.

2. **`tmp/` directory creation**: The executor creates the `tmp/` directory at
   startup if it does not exist (in `_read_status_file` or by ensuring the parent
   exists before the agent runs). Agents cannot rely on it existing.

3. **No other communication channel**: The stdout-based approach (Fix Option 2) would
   require changes to the streaming output parser. Moving the file (Fix Option 1) is
   simpler and keeps the existing status file schema intact.

4. **No permission config change**: Allowlist-based fixes (Fix Option 3) depend on
   Claude Code internals that may change; moving the file is more robust.

5. **Single constant `STATUS_FILE_PATH`**: All code reads from the central constant in
   `paths.py`. The parallel executor has its own `WORKTREE_STATUS_FILE_RELATIVE`
   constant which must match.
