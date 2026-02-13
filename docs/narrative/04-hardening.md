# Chapter 4: Hardening (The Battle Scars)

**Commits:** `d52e0c8`, `afe5ccc` --- 2026-02-05 to 2026-02-06
**Titles:**
- "fix(orchestrator): Delete stale branches before creating worktrees"
- "feat(orchestrator): graceful stop semaphore and claude binary resolution"

These two commits represent the transition from "it works in theory" to "it survives
in practice." Each fix addresses a real failure mode encountered during production use.

## Fix 1: Stale Branches (`d52e0c8`)

**The Problem:** When a parallel run fails or is interrupted, worktree branches
(`parallel/1-1`, `parallel/1-2`, etc.) are left behind. The next run tries to create
a branch with the same name and fails:

```
fatal: A branch named 'parallel/1-1' already exists.
```

**The Fix:** Before creating a worktree, aggressively clean up:

```python
def create_worktree(plan_name, task_id):
    branch_name = f"parallel/{task_id.replace('.', '-')}"

    # Delete stale branch if it exists (from previous failed run)
    subprocess.run(
        ["git", "branch", "-D", branch_name],
        capture_output=True, text=True, check=False  # Don't fail if branch doesn't exist
    )

    # Prune any stale worktree references
    subprocess.run(
        ["git", "worktree", "prune"],
        capture_output=True, text=True, check=False
    )

    # Now create the worktree
    subprocess.run(
        ["git", "worktree", "add", "-b", branch_name, str(worktree_path)],
        ...
    )
```

Note `check=False` --- we don't care if the branch doesn't exist. We just want to ensure
a clean slate. The `git worktree prune` also cleans up references to worktrees that were
manually deleted.

**Lesson:** Infrastructure code that creates temporary resources must always clean up
stale resources from previous runs. Never assume the previous run cleaned up after itself.

## Fix 2: Graceful Stop (`afe5ccc`)

**The Problem:** The orchestrator runs unattended, potentially for hours. Sometimes you
need to stop it --- for a code review, to investigate a failure, or because it's heading
in the wrong direction. Killing the process with Ctrl+C or `kill` leaves:
- The current task's Claude process orphaned (PPID becomes 1)
- The YAML plan in an inconsistent state (task marked "in_progress" forever)
- Worktrees not cleaned up

**The Solution:** A semaphore file:

```python
STOP_SEMAPHORE_PATH = ".claude/plans/.stop"

def check_stop_requested():
    if os.path.exists(STOP_SEMAPHORE_PATH):
        return True
    return False
```

To stop gracefully: `touch .claude/plans/.stop`

The orchestrator checks for this file before starting each new task. It finishes the
current task, saves the plan, and exits cleanly. The semaphore is cleared on startup
to prevent stale stops from blocking the next run.

```python
# In the main loop:
while True:
    if check_stop_requested():
        print(f"Graceful stop requested")
        os.remove(STOP_SEMAPHORE_PATH)
        break

    result = find_next_task(plan)
    ...
```

The startup banner now advertises this:

```
=== Plan Orchestrator ===
Plan: Volunteer Dashboard Enhancement
Claude binary: /opt/homebrew/lib/node_modules/@anthropic-ai/claude-code/cli.js
Graceful stop: touch .claude/plans/.stop
```

## Fix 3: Claude Binary Resolution (`afe5ccc`)

**The Problem:** When the orchestrator spawns subprocesses (for parallel tasks in
worktrees), the child process's PATH doesn't always include the Claude CLI. On macOS
with Homebrew, the `claude` binary might be at a non-standard location.

**The Fix:** A multi-strategy binary resolution function:

```python
CLAUDE_BINARY_SEARCH_PATHS = [
    "/opt/homebrew/lib/node_modules/@anthropic-ai/claude-code/cli.js",
    "/usr/local/lib/node_modules/@anthropic-ai/claude-code/cli.js",
]

def resolve_claude_binary() -> list[str]:
    # Strategy 1: Check PATH
    claude_path = shutil.which("claude")
    if claude_path:
        return [claude_path]

    # Strategy 2: Known installation paths
    for search_path in CLAUDE_BINARY_SEARCH_PATHS:
        if os.path.isfile(search_path):
            node_path = shutil.which("node")
            if node_path:
                return [node_path, search_path]

    # Strategy 3: npx fallback
    npx_path = shutil.which("npx")
    if npx_path:
        return [npx_path, "@anthropic-ai/claude-code"]

    # Strategy 4: Hope for the best
    return ["claude"]
```

The resolved command is stored in a global `CLAUDE_CMD` and used everywhere:

```python
cmd = [*CLAUDE_CMD, "--dangerously-skip-permissions", "--print", prompt]
```

**Lesson:** Never assume a binary is on PATH in subprocess environments. Resolve the
full path at startup and reuse it.

## Fix 4: Stale task-status.json in Worktrees (`7226315` --- 2026-02-09)

**The Problem:** When a git worktree is created from the main branch, it inherits all
files --- including `.claude/plans/task-status.json` from the *previous* task's run.
The new Claude session would find this old status file and the orchestrator would read
stale results.

**The Fix:** Delete the status file immediately after creating a worktree:

```python
def create_worktree(plan_name, task_id):
    # ... create worktree ...

    # Clear stale task-status.json inherited from main branch
    stale_status = worktree_path / ".claude" / "plans" / "task-status.json"
    if stale_status.exists():
        stale_status.unlink()
        verbose_log("Removed stale task-status.json from worktree", "WORKTREE")

    return worktree_path
```

**Lesson:** Worktrees inherit the full working tree. Any file used as a communication
channel between the orchestrator and Claude must be cleared in new worktrees to prevent
cross-contamination from previous runs.

## The Verbose Logging System

Also introduced in the Phase 0 commit was a comprehensive verbose logging system:

```python
VERBOSE = False

def verbose_log(message, prefix="VERBOSE"):
    if VERBOSE:
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"[{timestamp}] [{prefix}] {message}", flush=True)
```

Every significant operation got verbose logging with prefixes like `[FIND]`, `[DEPS]`,
`[WORKTREE]`, `[PARALLEL]`, `[CLEANUP]`, `[EXEC]`. This proved invaluable for
debugging the parallel execution issues that followed.

## Questions

**Q: Why a file-based semaphore instead of Unix signals?**
Signals (SIGUSR1, etc.) would require knowing the orchestrator's PID. The file approach
is simpler: `touch .claude/plans/.stop` works from any terminal, any script, or even
from within a Claude session. It's also cross-platform (though this project only runs
on macOS).

**Q: Why hardcode Homebrew paths for Claude binary resolution?**
This is macOS-specific and fragile. A more robust approach would be to read the npm
global prefix (`npm config get prefix`) and construct the path. However, the current
approach works reliably for the actual development environment and the three fallback
strategies cover edge cases.

**Q: Is there a risk of orphaned Claude processes even with graceful stop?**
Yes. The graceful stop only prevents *new* tasks from starting. The currently running
Claude process will finish (or timeout). If the orchestrator is killed with SIGKILL,
the Claude process becomes orphaned (PPID=1). The MEMORY.md documents this: "killing
orchestrator orphans child Claude (PPID=1) - kill separately."
