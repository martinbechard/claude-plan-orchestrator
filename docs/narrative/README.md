# The Plan Orchestrator: A Narrative History

This folder documents the evolution of the Plan Orchestrator --- the automated task execution
engine built during the development of CheapoVille, a community open-source tool that empowers
non-profit organizations with a free management platform that costs almost nothing to operate.
The orchestrator allows a human-AI team to break down large features into YAML plans and have
Claude execute each task in a fresh session, avoiding the context degradation that plagues
long-running LLM interactions.

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

Current: ~2000 lines (orchestrator) + 1073 lines (auto-pipeline)
Plans executed: 19 YAML plan files, 11+ completed plans
```

## The Core Insight

LLMs degrade on long-running tasks. Context accumulates, quality drops, implementation details
get contradicted. The orchestrator exists to give each task a *fresh* Claude session with clean
context, while a Python script manages the state machine of plan progression. This architectural
decision---splitting the "what to do" (YAML) from the "do it" (Claude) from the "manage it"
(Python)---is the foundation everything else builds on.
