# The Plan Orchestrator: A Narrative History

## I, Claudius...

Herein are recorded the chronicles of a roll-your-own agent orchestration tool, told from
the point of view of the AI that built it --- with a little human help, mostly in the form
of good (and sometimes not so good) suggestions. Every line of code, every design document,
every work item, every test, and every commit: mine. The human brought the vision, the
impatience, and the occasional 2 AM nudge in a better direction. I brought the keystrokes.
All three thousand lines of them.

What follows is the story of how a 454-line Python script grew into a parallel execution
engine that designs its own features, judges its own designs, extends its own plans, and
only bothers the human when something catches fire.

---

This folder documents the evolution of the Plan Orchestrator --- the automated task execution
engine built during the development of CheapoVille, a full-featured open-source online community
platform --- a social hub with blogs, instant messaging, help-wanted boards, and more.
The orchestrator breaks down large features into YAML plans and has Claude execute each task
in a fresh session, avoiding the context degradation that plagues long-running LLM interactions.
Design competitions with an AI judge validate plans automatically; the human only intervenes
when the circuit breaker trips or smoke tests fail.

## Document Index

| File | Contents |
|------|----------|
| [01-genesis.md](01-genesis.md) | The original 454-line orchestrator: why it was built, how it worked, the YAML plan schema |
| [02-parallel-execution.md](02-parallel-execution.md) | The big leap: git worktrees, parallel task groups, conflict detection, circuit breakers |
| [03-coordination-protocol.md](03-coordination-protocol.md) | Subagent coordination: file claims, heartbeats, stale claim cleanup |
| [04-hardening.md](04-hardening.md) | Battle scars: graceful stop, binary resolution, stale branches, stale task-status.json |
| [05-rate-limits-and-resilience.md](05-rate-limits-and-resilience.md) | Rate limit detection, auto-retry, timezone-aware wait logic |
| [06-smoke-tests-and-streaming.md](06-smoke-tests-and-streaming.md) | Post-plan smoke tests, real-time stream-json output for verbose mode |
| [07-auto-pipeline.md](07-auto-pipeline.md) | The meta-layer: auto-pipeline daemon that watches backlogs and drives the orchestrator |
| [08-lessons-and-questions.md](08-lessons-and-questions.md) | Lessons learned, open questions, and patterns that emerged |
| [09-fixing-parallel-merge.md](09-fixing-parallel-merge.md) | Fixing the root cause: replacing git merge with file-copy for parallel worktrees |
| [10-design-competitions.md](10-design-competitions.md) | The evolving implement skill: parallel design generation, AI judge, and self-extending plans |

## Timeline at a Glance

```
2026-01-19  Genesis: 454 lines, sequential execution, YAML plans
2026-02-05  Parallel execution via git worktrees (+600 lines)
2026-02-05  Subagent coordination protocol (claims, heartbeats)
2026-02-05  Stale branch cleanup fix
2026-02-06  Graceful stop semaphore + claude binary resolution
2026-02-09  Rate limit detection and auto-retry
2026-02-09  Stale task-status.json worktree fix
2026-02-10  Post-plan smoke test infrastructure
2026-02-12  Stream-json real-time output
2026-02-12  Auto-pipeline daemon (separate script, 1073 lines)
2026-02-12  Fix parallel merge: file-copy replaces git merge
2026-02-07+ Design competition pattern (Phase 0) across 7 plans

Current: ~2000 lines (orchestrator) + 1073 lines (auto-pipeline)
Plans executed: 19 YAML plan files, 11+ completed plans
```

## The Core Insight

LLMs degrade on long-running tasks. Context accumulates, quality drops, implementation details
get contradicted. The orchestrator exists to give each task a *fresh* Claude session with clean
context, while a Python script manages the state machine of plan progression. This architectural
decision---splitting the "what to do" (YAML) from the "do it" (Claude) from the "manage it"
(Python)---is the foundation everything else builds on.
