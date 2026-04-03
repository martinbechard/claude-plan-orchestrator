# Planner Skill: Plan Quality Criteria

- **GRANULAR TASKS:** This is the most important rule. Each task must address
  ONE specific problem or change. A task that says "fix the traces page" is too
  large. Break it into: "fix LangGraph names in root traces", "merge duplicate
  start/end rows", "remove redundant slug column", "show real cost", etc.
  A plan with 8-12 focused tasks is BETTER than a plan with 2-3 big tasks.
  Each task should have a clear, independently verifiable outcome.
- **Session-Sized Tasks:** Each task must be completable in one Claude session
  (under 10 minutes). If a task seems too large, split it into subtasks.
- **Specific File Paths:** Task descriptions must include the exact file paths to
  create or modify. Never leave the implementer guessing which files to touch.
- **Valid DAG:** Dependencies must form a directed acyclic graph. No circular
  dependencies allowed.
- **Build Order:** Follow the docs -> code -> tests -> verification order within
  each section. Create interfaces before implementations, implementations before
  tests.
- **Reference Lines:** When modifying existing files, reference approximate line
  numbers or surrounding code landmarks to help the implementer locate the right
  section.
