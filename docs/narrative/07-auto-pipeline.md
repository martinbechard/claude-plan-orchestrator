# Chapter 7: The Auto-Pipeline

**Commit:** `0c0c681` --- 2026-02-12
**Size:** 827 lines (new file: `scripts/auto-pipeline.py`)
**Title:** "feat: add auto-pipeline tool for automated backlog processing"

## The Meta-Layer

The auto-pipeline represents the final level of automation abstraction:

```
Level 0: Human writes code
Level 1: Claude writes code (interactive session)
Level 2: Orchestrator runs Claude (YAML plan, fresh sessions per task)
Level 3: Auto-pipeline drives the orchestrator (watches backlogs, creates plans)
```

At Level 3, the human's role shifts from "write code" to "write backlog items."
The auto-pipeline watches `docs/defect-backlog/` and `docs/feature-backlog/` for
new markdown files, generates YAML plans via Claude, executes them via the orchestrator,
and archives completed items.

## How It Works

### Phase 1: Detection

The auto-pipeline uses `watchdog` for filesystem events plus a 60-second periodic scan:

```python
class BacklogHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.src_path.endswith('.md'):
            self.pipeline.queue_item(event.src_path)

# Plus safety fallback
while True:
    scan_for_new_items()
    time.sleep(60)
```

Items are skipped if they:
- Contain `## Status: Fixed` or `## Status: Completed`
- Live in a `completed/` subdirectory
- Have already failed in this session (no retry)

Priority order: defects first (alphabetically), then features (alphabetically).

### Phase 2: Plan Creation

For each backlog item, the auto-pipeline spawns Claude to create a design document
and YAML plan:

```python
prompt = f"""Read the backlog item at {item_path}.
Create:
1. A design document at docs/plans/YYYY-MM-DD-{feature_name}-design.md
2. A YAML plan at .claude/plans/{feature_name}.yaml

Follow the YAML plan schema used by other plans in .claude/plans/.
"""

subprocess.run([*CLAUDE_CMD, "--dangerously-skip-permissions", "--print", prompt])
```

### Phase 3: Orchestrator Execution

The auto-pipeline then invokes the orchestrator on the generated plan:

```python
subprocess.run([
    "python", "scripts/plan-orchestrator.py",
    "--plan", f".claude/plans/{feature_name}.yaml"
])
```

### Phase 4: Archive

On success, the backlog item is moved to the `completed/` subdirectory.

## Dev Server Management

A practical detail: the orchestrator's tasks often need a running dev server for
builds and tests, but the dev server's `.next` cache can conflict with the build step.
The auto-pipeline manages this:

```python
# Before orchestrator run
stop_dev_server()
# Run orchestrator (which runs pnpm run build in tasks)
run_orchestrator(plan_path)
# After orchestrator run
start_dev_server()
```

## Subsequent Fixes (Same Day)

The auto-pipeline went through rapid iteration on 2026-02-12:

| Commit | Fix |
|--------|-----|
| `df74a1d` | Stream child process output in real-time with `PYTHONUNBUFFERED` |
| `aece5eb` | Prevent terminal corruption by detaching stdin from children |
| `b3d03b6` | Reset interrupted tasks on recovery to prevent burnt retries |
| `4d2eca6` | Add recovery support for interrupted runs |
| `3135beb` | Auto-stop/restart dev server around orchestrator runs |
| `a381985` | Add timestamps to streamed child process output |
| `ae0a9c8` | Pass `--verbose` to orchestrator when auto-pipeline is verbose |
| `8228103` | Stream-json output (see Chapter 6) |

This rapid sequence of fixes (8 commits in one day) reveals the typical pattern:
a feature works conceptually but encounters practical issues around process management,
terminal handling, and state recovery.

## The Recovery Mechanism

One particularly important fix: recovery from interrupted runs. If the auto-pipeline
is killed while an orchestrator is running, the YAML plan has tasks marked "in_progress"
that never completed. On restart:

```python
def recover_interrupted_plan(plan_path):
    plan = load_plan(plan_path)
    for section in plan.get("sections", []):
        for task in section.get("tasks", []):
            if task.get("status") == "in_progress":
                task["status"] = "pending"
                task["attempts"] = max(0, task.get("attempts", 1) - 1)
    save_plan(plan_path, plan)
```

This resets interrupted tasks to "pending" without counting the interrupted run as a
failed attempt --- the same principle as rate limit handling.

## Shared Stop Semaphore

The auto-pipeline respects the same `.claude/plans/.stop` semaphore as the orchestrator.
Touching this file stops both the current orchestrator run *and* prevents the auto-pipeline
from starting the next backlog item. One command stops the entire automation stack.

## Questions

**Q: Is this "AI writing AI plans" --- does it work?**
In practice, the quality of auto-generated plans varies. Simple defect fixes produce
clean, executable plans. Complex features sometimes produce plans with unrealistic task
decompositions or missing dependencies. The human still reviews the generated design
document and YAML plan before the orchestrator executes. The auto-pipeline automates
the *scaffolding*, not the *judgment*.

**Q: Why a separate script instead of extending the orchestrator?**
The MEMORY.md explicitly warns against nested orchestrators: "Nested orchestrators cause
status file races, worktree collisions, 600s timeout too short, rate limit cascading,
file claim conflicts." The auto-pipeline avoids this by being a *driver* of the
orchestrator, not a wrapper around it. It's a peer process, not a parent process.

**Q: What prevents the auto-pipeline from running indefinitely?**
The `--once` flag processes one item and exits. Without it, the daemon runs until
stopped via Ctrl+C or the stop semaphore. There's no built-in limit on how many items
it processes, which means a large backlog could trigger hours of automated execution.
The stop semaphore is the safety valve.

**Q: How does cost control work?**
It doesn't, explicitly. Each Claude session has its own token budget, and the rate
limit detection (Chapter 5) provides a natural throttle. But there's no total cost
cap across a pipeline run. This is a deliberate omission --- the human is expected
to monitor costs through Anthropic's dashboard and use the stop semaphore if costs
are concerning.
