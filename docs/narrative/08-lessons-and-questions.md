# Chapter 8: Lessons Learned and Open Questions

## Growth by the Numbers

| Metric | Genesis (Jan 19) | Final (Feb 12) |
|--------|------------------|-----------------|
| Orchestrator lines | 454 | 1,957 |
| Auto-pipeline lines | --- | 1,073 |
| Total automation code | 454 | 3,030 |
| YAML plan files | 1 | 19 |
| Completed plans | 0 | 11+ |
| Functions | 8 | ~35 |
| CLI arguments | 4 | 8 |

The orchestrator grew 4.3x in 24 days. Every addition was reactive --- prompted by a
real failure or operational need, not speculative design.

## The Pattern of Evolution

Looking at the commit timeline, a clear pattern emerges:

```
Feature commit  ->  Bug fix  ->  Bug fix  ->  Next feature
```

Each major feature (parallel execution, rate limits, auto-pipeline) was followed by
multiple fix commits. This isn't sloppy engineering --- it's the reality of building
infrastructure that manages AI agents. The failure modes are inherently unpredictable
because the agents themselves are unpredictable.

## Key Lessons

### 1. Fresh Context Beats Long Context

The orchestrator's entire raison d'etre is giving each task a fresh Claude session.
This was validated repeatedly: the same task that fails in a long-running session
succeeds when run fresh. The context degradation in LLMs is real and measurable.

### 2. Communication Channels Must Be Explicit

The task-status.json file, the agent-claims.json, the subagent status files --- all
are explicit, file-based communication channels. The alternative (parsing Claude's
text output to determine success/failure) was tried and abandoned early. Structured
communication is essential for reliable automation.

### 3. Parallel Execution is Harder Than It Looks

The parallel execution story (Chapters 2-3) shows the classic distributed systems
lesson: correctness is hard. The conflict detection, worktree management, merge
strategy, file claims, and stale cleanup all address real problems. And the merge
strategy *still* had a bug (not copying new files) that required manual intervention.

### 4. Resilience Features Are the Majority of the Code

The "happy path" of the orchestrator (find task, run Claude, update status) is about
100 lines. The remaining ~1,800 lines handle: retries, circuit breakers, rate limits,
graceful stops, binary resolution, stale cleanup, verbose logging, smoke tests,
parallel execution, conflict detection, worktree management, and stream-json output.
This 18:1 ratio of resilience-to-core is typical of production infrastructure.

### 5. Human Oversight Points Matter

Every automation level includes escape hatches:
- **Stop semaphore:** `touch .claude/plans/.stop`
- **Ctrl+C during rate limit waits:** aborts cleanly
- **--single-task:** run one task then stop
- **--dry-run:** preview without executing
- **--skip-smoke:** bypass post-plan verification
- **Verbose mode:** see exactly what Claude is doing

These aren't afterthoughts --- they were added because the human operator needed them
in real situations.

### 6. The Self-Extending Plan Pattern

One of the most elegant patterns that emerged: Claude can modify its own plan.
Task 3.2 in a verification phase ran E2E tests, discovered a defect, and
*extended the YAML plan* with a new task 4.1 to fix it. The orchestrator reloaded
the plan and continued.

This turns the plan from a static document into a dynamic program, where the AI
adapts its own execution path based on what it discovers. It's a form of
meta-programming --- the AI is programming its own future sessions.

## Open Questions

### Architecture Questions

**Q: Should the orchestrator be rewritten in TypeScript?**
The project is a TypeScript application, and having the orchestrator in Python creates
a language barrier. However, Python's subprocess management, YAML handling, and
scripting ergonomics are genuinely better for this use case. The "right" language for
the orchestrator is different from the "right" language for the application.

**Q: Could the YAML plans be replaced with a database?**
A SQLite database would solve the concurrent-access issues with the YAML files (race
conditions during parallel execution, YAML formatting inconsistencies). But YAML plans
have advantages: they're human-readable, git-diffable, and Claude can modify them
directly. A database would require a separate admin interface.

**Q: Is the 600-second timeout fundamentally wrong?**
Some tasks consistently hit the timeout. The timeout exists to prevent runaway sessions,
but it also kills legitimate work. An adaptive timeout (based on task complexity or
historical duration) would be more sophisticated but harder to tune.

### Scaling Questions

**Q: What happens with 50+ task plans?**
The largest completed plan had 59 tasks (activity feed widget). The orchestrator handled
it but encountered status synchronization issues in parallel mode. Larger plans might
benefit from being split into sub-plans with explicit handoff points.

**Q: Could multiple orchestrators run simultaneously?**
Currently, no. The status file, claims file, and YAML plan are shared state that
assumes a single orchestrator. Running two orchestrators would require per-orchestrator
namespacing of all coordination files. The auto-pipeline avoids this by running
orchestrators sequentially.

**Q: What about cost optimization?**
The orchestrator has no concept of cost. Each task gets the same model (currently
Opus 4.6) regardless of complexity. A cost-aware system might use Sonnet for simple
tasks and Opus for complex ones, but this requires task-level complexity classification
that doesn't exist in the current YAML schema.

### Philosophical Questions

**Q: At what point does the automation overhead exceed the benefit?**
The orchestrator + auto-pipeline is ~3,000 lines of Python managing AI sessions that
write TypeScript. If the project were smaller, this would be over-engineering. For a
project with 11+ completed plans and 19 YAML plans, the investment has paid for itself
many times over. But there's a complexity ceiling --- each new feature in the orchestrator
is itself code that can have bugs.

**Q: Is this a general-purpose tool or project-specific?**
The orchestrator is *almost* general-purpose. It depends on `pnpm run build` being the
build command (hardcoded in prompts), Playwright for smoke tests, and the project's
specific file structure in prompts. Extracting it into a reusable tool would require
parameterizing these assumptions, which is feasible but hasn't been done.

**Q: What would a v2 look like?**
Based on the lessons learned, a v2 might:
- Use SQLite for state instead of YAML/JSON files
- Have a proper merge strategy for parallel tasks (full git merge, not YAML-only)
- Support task-level model selection
- Include cost tracking and budgets
- Have a web dashboard for monitoring
- Support distributed execution (multiple machines)

But the current v1 works. And in the spirit of this project's philosophy ---
"prioritize simplicity and stability" --- a v2 would only be justified if v1
becomes a bottleneck.

## The Narrative Arc

The orchestrator's story is one of **progressive discovery.** It started as a simple
loop (find task, run Claude, repeat) and grew into a sophisticated state machine
through encounter with real-world failures. Each commit represents a lesson learned
the hard way:

- Stale branches taught cleanup-before-create
- Orphaned processes taught graceful stop
- Rate limits taught patience
- Stale status files taught cross-contamination awareness
- Broken builds taught post-plan verification
- Silent failures taught verbose logging

The result is a system that reliably executes multi-task plans with an AI developer,
handles failures gracefully, and gives the human operator enough visibility and
control to trust the automation. It's not elegant --- it's practical. And that's
exactly what infrastructure should be.
