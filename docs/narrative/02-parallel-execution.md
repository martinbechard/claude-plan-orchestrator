# Chapter 2: Parallel Execution

**Commit:** `a829735` --- 2026-02-05
**Size:** ~600 new lines
**Title:** "feat(orchestrator): Add parallel agent coordination mechanism"

## The Motivation

By early February, the orchestrator had successfully executed several plans sequentially.
But plans were getting larger --- the Volunteer Dashboard Enhancement plan had dozens of tasks ---
and many of them were independent. Running them one at a time was leaving performance on
the table.

The insight: if two tasks modify completely separate files, they can run simultaneously
in isolated git worktrees.

## The Git Worktree Strategy

Git worktrees allow multiple working directories from the same repository, each on a
different branch. The orchestrator exploits this:

```
Main branch (orchestrator lives here)
  |
  +-- .worktrees/plan-task-1-1/  (branch: parallel/1-1)
  +-- .worktrees/plan-task-1-2/  (branch: parallel/1-2)
  +-- .worktrees/plan-task-1-3/  (branch: parallel/1-3)
```

Each parallel task gets its own worktree, runs in isolation, and the orchestrator
merges results back to main when all tasks in a group complete.

```python
def create_worktree(plan_name: str, task_id: str) -> Optional[Path]:
    worktree_path = get_worktree_path(plan_name, task_id)
    branch_name = f"parallel/{task_id.replace('.', '-')}"
    subprocess.run(
        ["git", "worktree", "add", "-b", branch_name, str(worktree_path)],
        capture_output=True, text=True, check=True
    )
    return worktree_path
```

## Parallel Groups in YAML

Tasks declare their parallel eligibility:

```yaml
tasks:
- id: '8.1'
  name: Add donation settings to organization edit form
  parallel_group: phase-8-admin
  exclusive_resources: []
- id: '8.2'
  name: Build embed code generation modal
  parallel_group: phase-8-admin
  exclusive_resources: []
- id: '8.3'
  name: Create preview pane for donation widget
  parallel_group: phase-8-admin
  exclusive_resources: []
```

The orchestrator finds all pending tasks with the same `parallel_group`, checks they
have no conflicts, and runs them concurrently using `ThreadPoolExecutor`.

## Conflict Detection

Before launching parallel tasks, the orchestrator performs two checks:

**1. File-Level Conflict Detection**
Parses task descriptions for file paths and checks for overlaps:

```python
def extract_files_from_description(description: str) -> set[str]:
    """Extract file paths mentioned in a task description."""
    # Pattern for standalone file paths (src/..., test/..., etc.)
    path_pattern = r'\b((?:src|test|lib|app|components|hooks|pages|api)/
        [\w\-./]+\.(?:tsx?|jsx?|md|json|yaml|css|scss))\b'
    for match in re.finditer(path_pattern, description):
        files.add(match.group(1))
    return files
```

**2. Exclusive Resource Detection**
Tasks can declare resources they need exclusive access to:

```yaml
- id: '3.1'
  exclusive_resources: ['database']  # Can't share database access
```

If any pair of tasks has overlapping files or exclusive resources, the entire group
falls back to sequential execution:

```python
def check_parallel_task_conflicts(tasks):
    # ... extract files from each task description ...
    overlap = files1 & files2
    if overlap:
        return (True, f"Tasks {id1} and {id2} both modify: {', '.join(overlap)}")
    resource_overlap = res1 & res2
    if resource_overlap:
        return (True, f"Tasks {id1} and {id2} both require: {', '.join(resource_overlap)}")
    return (False, "")
```

## The Circuit Breaker

This commit also introduced the `CircuitBreaker` class --- a pattern borrowed from
distributed systems. If 3 consecutive tasks fail (suggesting the LLM is unavailable
or fundamentally broken), the orchestrator stops spawning new tasks and waits for a
reset timeout (default 300 seconds).

```python
class CircuitBreaker:
    def __init__(self, threshold=3, reset_timeout=300):
        self.threshold = threshold
        self.consecutive_failures = 0
        self.is_open = False

    def record_failure(self):
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.threshold:
            self.is_open = True
            print(f"[CIRCUIT BREAKER] Tripped after {self.consecutive_failures} failures")

    def can_proceed(self) -> bool:
        if not self.is_open:
            return True
        # Check if enough time has passed for retry
        elapsed = time.time() - self.last_failure_time
        if elapsed >= self.reset_timeout:
            self.is_open = False
            return True
        return False
```

This prevents the orchestrator from burning through all retry attempts on every remaining
task when the root cause is systemic (API outage, rate limit, etc.).

## The Merge Problem (Later Fixed --- See Chapter 9)

The most consequential lesson from parallel execution was discovered later (commits
`b8004a3`, `14a307c`, `6856c34`): **parallel branches all modified the YAML plan file,
causing merge conflicts that silently prevented code files from reaching main.**

The `merge_worktree()` function used `git merge --no-ff`, which is correct for a single
branch. But when merging multiple parallel branches sequentially, the first merge
advances HEAD, causing YAML conflicts for the remaining branches. The conflicts caused
the merge to fail, and `cleanup_worktree` destroyed the unmerged code.

Commit `14a307c` tells the story:

> "Cherry-picked test files from parallel/9-6, 9-7, 9-8 branches that were not merged
>  to main by the parallel group merge."

This was **fixed in Chapter 9** by replacing `git merge` with a file-copy strategy
(`copy_worktree_artifacts`) that copies changed files from worktrees while skipping
coordination files the orchestrator manages. The `--parallel` flag is now safe for all
task types including those that create new files.

## Dependency Tracking

The parallel execution commit also added proper dependency checking:

```python
def check_dependencies_satisfied(plan, depends_on):
    for dep_id in depends_on:
        result = find_task_by_id(plan, dep_id)
        if not result:
            return False
        _, dep_task = result
        if dep_task.get("status") != "completed":
            return False
    return True
```

Tasks with `depends_on` fields are skipped until their dependencies complete, enabling
complex DAG-like execution orders within a plan.

## Questions

**Q: Why ThreadPoolExecutor instead of multiprocessing?**
Since each parallel task spawns a separate `claude` CLI process in its own worktree,
the actual work happens in child processes. The Python threads are just waiting for
subprocess completion. ThreadPoolExecutor is simpler and avoids the serialization
overhead of multiprocessing.

**Q: Why regex-based file conflict detection instead of a proper manifest?**
This is arguably the weakest part of the parallel system. Parsing file paths from
free-text descriptions is inherently fragile. A better approach might be to require
explicit `files_modified` arrays in the YAML. However, the current approach avoids
requiring plan authors to predict every file Claude will touch --- which is difficult
since Claude may discover additional files need modification during implementation.

**Q: Why didn't the merge handle new files?**
The original `git merge` approach should have handled new files, but the cascading
YAML conflicts prevented it from reaching them. See Chapter 9 for the full diagnosis
and the file-copy fix that resolved this.
