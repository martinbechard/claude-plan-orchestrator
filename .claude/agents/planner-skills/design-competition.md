# Planner Skill: Phase 0 Design Competitions

When the work item calls for multiple design approaches to be evaluated, create a
Phase 0 section with parallel design tasks and a judge task:

- Assign design tasks to "systems-designer", "ux-designer", or "frontend-coder"
  with the same parallel_group so they run concurrently.
- Assign the judge task (task 0.6 pattern) to "design-judge" -- never to "coder"
  or "ux-designer". The design-judge agent uses Opus and always declares a winner
  autonomously without suspending for human input.
- The judge task must depend_on all design tasks so it runs after all designs exist.
- Follow the judge task with a "planner" task (0.7 pattern) that reads the winning
  design and extends the YAML plan with implementation phases.
