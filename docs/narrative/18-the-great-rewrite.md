# Chapter 18: The Great Rewrite

**Period:** 2026-02-26 to 2026-03-23
**Size:** ~9300 lines of monolithic scripts replaced by ~2500 lines across 25 modular files in `langgraph_pipeline/`

## The Problem with Nine Thousand Lines

By late February, the orchestrator had grown into two monolithic Python scripts: `plan-orchestrator.py` at ~6100 lines and `auto-pipeline.py` at ~3200 lines. Every new feature --- Slack integration, RAG deduplication, model escalation, budget tracking, parallel worktrees, circuit breaking --- had been bolted onto these two files. They worked, but they were becoming difficult to reason about, difficult to test, and difficult for other projects to adopt.

The worst symptom was the import hack. `auto-pipeline.py` needed `SlackNotifier` from `plan-orchestrator.py`, but you cannot import from a file with a hyphen in its name using normal Python imports. So it used this:

```python
import importlib.util
_po_spec = importlib.util.spec_from_file_location(
    "plan_orchestrator", "scripts/plan-orchestrator.py")
_po_mod = importlib.util.module_from_spec(_po_spec)
_po_spec.loader.exec_module(_po_mod)
SlackNotifier = _po_mod.SlackNotifier
```

Eight symbols imported this way. One from a 6100-line file into a 3200-line file. Both scripts were simultaneously the orchestrator's public API, its internal implementation, and its entry points.

## The Decision: LangGraph

The rewrite used LangGraph --- a graph execution framework built on top of LangChain --- for two reasons:

1. **The pipeline was already a state machine.** The auto-pipeline scanned backlogs, created plans, executed tasks, verified defects, and archived results. These were nodes in a graph with conditional edges. The code just did not express them that way.

2. **Crash recovery for free.** LangGraph provides `SqliteSaver`, a checkpointer that persists graph state to SQLite after each node completes. If the process crashes, it resumes from the last completed node on restart. The old scripts had no crash recovery --- a kill mid-plan meant manual cleanup.

## The Architecture

Two interconnected graphs replaced the two monolithic scripts:

**Pipeline Graph** (6 nodes) replaced `auto-pipeline.py`:
- `scan_backlog` -- find next work item from backlog directories
- `intake_analyze` -- 5 Whys analysis, RAG dedup check
- `create_plan` -- design doc + YAML plan via Claude
- `execute_plan` -- invoke the executor subgraph
- `verify_symptoms` -- defect verification (conditional: defects only)
- `archive` -- move to completed

**Executor Subgraph** (4 nodes) replaced `plan-orchestrator.py`:
- `task_selector` -- pick next task respecting dependencies and parallel groups
- `task_runner` -- run Claude CLI in a fresh session
- `validator` -- check task-status.json, run validation agents
- Loop back to `task_selector` until done or circuit breaker trips

Each file is small: `scan.py` is ~120 lines, `task_runner.py` is ~150 lines. Contrast with the old `plan-orchestrator.py` where task selection, execution, validation, Slack notifications, model escalation, budget tracking, and circuit breaking were all interleaved in a single event loop.

## The Slack Decomposition

The Slack integration got the most dramatic improvement. The old `SlackNotifier` was a single 800-line class inside `plan-orchestrator.py` that handled outbound messaging, inbound polling, question/answer flows, agent identity, and loop prevention --- all in one place.

The new structure splits it into four focused modules:

- `slack/notifier.py` -- outbound messaging, Block Kit formatting, channel discovery
- `slack/poller.py` -- background polling thread, LLM-powered message routing, loop prevention
- `slack/suspension.py` -- Q&A flows, 5 Whys intake analysis
- `slack/identity.py` -- agent names, message signing, self-loop filtering

A `SlackNotifier` facade in `slack/__init__.py` composes these four modules, preserving the same external interface. Code that calls `slack.send_status()` or `slack.start_background_polling()` works unchanged.

## The Drop-In Replacement

Other projects had already adopted the orchestrator. They ran `python scripts/auto-pipeline.py` with flags like `--once`, `--verbose`, and `--dry-run`. Breaking that invocation would force a synchronized migration across all consumers.

The solution: `scripts/auto-pipeline.py` became a 19-line wrapper:

```python
from langgraph_pipeline.cli import main

if __name__ == "__main__":
    sys.exit(main())
```

The new CLI in `langgraph_pipeline/cli.py` accepts all the old flags (`--once`, `--verbose`, `--dry-run`) alongside new ones (`--budget-cap`, `--no-slack`, `--no-tracing`, `--single-item`). Projects using the old invocation see no change. Projects wanting the new features can use `python -m langgraph_pipeline` with the extended flag set.

## The README Rewrite

The README had accumulated 17 months of features documented against the old scripts. Every code example referenced `python scripts/plan-orchestrator.py --plan ...` with flags that no longer existed in the new CLI. The model escalation section showed `--starting-model` and `--max-model` flags. The budget section showed `--quota-ceiling-usd`. None of these were CLI flags in the new architecture --- escalation is now internal to the executor subgraph, and budget limits are set per-plan in YAML metadata or per-session via `--budget-cap`.

The entire README was rewritten to document the current architecture:
- Architecture diagram showing the two LangGraph graphs
- Unified CLI reference table
- Directory structure showing the full `langgraph_pipeline/` module tree
- Feature documentation written against the current configuration mechanisms
- No comparative language ("new", "replaces", "formerly") --- the README describes the steady state

## What Was Preserved

Despite the scope of the rewrite, the external contract is unchanged:

- **Same entry point**: `python scripts/auto-pipeline.py`
- **Same CLI flags**: `--once`, `--verbose`, `--dry-run` all work
- **Same backlog format**: Markdown files in `docs/defect-backlog/` and `docs/feature-backlog/`
- **Same plan format**: YAML with sections, tasks, dependencies, parallel groups
- **Same Slack channels**: Same prefix pattern, same message formats
- **Same status protocol**: `.claude/plans/task-status.json` with the same schema
- **Same stop mechanism**: `.claude/plans/.stop` semaphore and PID file

The rewrite was invisible to consumers. The only new visible artifact is `.claude/pipeline-state.db` --- the SQLite checkpoint database that enables crash recovery.

## The Numbers

| Metric | Before | After |
|--------|--------|-------|
| Entry points | 2 scripts (9300 lines) | 1 package (25 files, ~2500 lines) |
| Largest file | 6100 lines | ~200 lines |
| Crash recovery | None | SQLite checkpointing |
| Import hacks | `importlib.util.spec_from_file_location` | Standard Python packages |
| Test isolation | Difficult (monolithic state) | Per-node unit testing |

## Lessons

**Monoliths are fine until they are not.** The two-script architecture served well through 17 chapters of features. It broke down when (a) the scripts needed to share code but could not import each other cleanly, and (b) the state machine became complex enough that crash recovery mattered.

**Graphs are state machines with checkpoints.** The LangGraph rewrite did not change what the code does. It changed how the code expresses what it does. Each node is a pure function from state to state. The graph framework handles sequencing, conditional branching, and persistence.

**Backward compatibility is a design constraint, not an afterthought.** The wrapper script was trivial to write but required the new CLI to accept the old flags. That meant adding `--once` and `--verbose` as first-class arguments, not as deprecated aliases.

## First Live Run: The Missing Wires

The rewrite looked complete on paper. Every node was implemented, every test passed, the README was polished. Then a consumer project tried to run it.

### Slack polling never started

`SlackNotifier()` was created but `start_background_polling()` was never called in `cli.py`. The cleanup code (`stop_background_polling`) existed in the `finally` block. The start call was simply missing --- a one-line omission that made the entire Slack integration silently inert.

### No LLM callback

`SlackNotifier` accepts a `call_claude` callback for LLM-powered operations: message routing, intake analysis, and Q&A. The old monolith defined `_call_claude_print()` as a method on the class. The new modular `cli.py` created `SlackNotifier()` without passing the callback. Result: every LLM call returned an empty string, every intake analysis produced `[INTAKE] LLM returned empty response`, and the message router silently fell through to `{"action": "none"}`.

The fix: a shared `call_claude()` function in `shared/claude_cli.py` that invokes `claude --print` as a subprocess and returns the result text. One function, passed to `SlackNotifier(call_claude=call_claude)`.

### Single-digit file numbering

The Slack intake created files like `1-slug.md`, but the backlog scanner required `\d{2,}` (two or more digits). Items 1-9 were silently skipped. One-character fix: `{next_num}` to `{next_num:02d}`.

### JSON parsing in the message router

The LLM message router called `json.loads(response)` on Claude's output, expecting pure JSON. But Claude wraps JSON in markdown code fences or adds preamble. The `_extract_json()` helper now tries: (1) direct parse, (2) code fence extraction, (3) inline `{...}` extraction.

### Haiku for everything

The model escalation system started every task at `haiku` regardless of agent type. A `frontend-coder` task (which declares `model: sonnet` in its frontmatter) was running on haiku and producing low-quality output. The fix: `find_next_task` now reads the agent's frontmatter model and uses it as a floor --- escalation can only go higher, never below the agent's declared minimum.

### LangSmith noise

With LangSmith enabled, every 15-second idle scan cycle sent 4+ traces to the API. The fix: run `scan_backlog` directly (no graph, no tracing) to check for work, then only invoke the full pipeline graph (with tracing) when an item is found.

Additionally, LangSmith configuration was changed to opt-in (`langsmith.enabled: true` required), with upfront validation of both `LANGSMITH_API_KEY` and `LANGSMITH_WORKSPACE_ID` before making any calls.

### Tool call tracing

The pipeline self-implemented its first feature backlog item: LangSmith tool call tracing. Each Claude CLI task execution now emits child spans for every tool call (Read, Edit, Bash, Grep, etc.) so the LangSmith dashboard shows what Claude did during each task, not just the final result.

### Archival commit gap

The archive node moved files and deleted plan YAMLs but never committed the changes, leaving a dirty working tree after each completed item. Now `_git_commit_archival()` stages and commits automatically.

### Environment secrets

A `.env.local` / `.env` loader was added so secrets (LangSmith API key, workspace ID, Slack tokens) can be kept out of config files and git history. `.env.local` is loaded first (plugin-specific), then `.env` (host project defaults). No third-party dependencies.

## The Pattern

Every issue followed the same pattern: the modular architecture was correct, but the wiring between modules was incomplete. The old monoliths had no wiring --- everything was methods on one class calling other methods on the same class. The new architecture required explicit connections: callbacks passed as constructor arguments, functions imported and called at the right moment, configuration loaded and validated before use.

Integration testing would have caught all of these. Unit tests verified that each node worked in isolation. What was missing was a test that started the pipeline, sent a Slack message, and verified the item appeared in the backlog.

## Lessons (continued)

**Unit tests are necessary but not sufficient.** 258 executor tests passed. The system did not work. Every failure was at the boundary between modules, which unit tests by design do not cover.

**The first live run is the real test.** The rewrite was "done" for three weeks before a consumer project tried it. Every issue above was discovered in the first hour of real use.

**Opt-in is safer than opt-out for external services.** LangSmith tracing defaulting to on with no validation produced a stream of error logs. Changing it to opt-in with credential validation eliminated an entire class of startup failures.
