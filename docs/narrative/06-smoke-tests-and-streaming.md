# Chapter 6: Smoke Tests and Streaming

**Commits:** `d715e13` (2026-02-10), `8228103` (2026-02-12)
**Titles:**
- "fix: auth layout conflict, middleware hardening, and smoke test infrastructure"
- "feat: add real-time stream-json output to plan orchestrator"

## Post-Plan Smoke Tests

### The Problem

A plan could complete all its tasks with "success" status, but the application could
still be broken. Tasks validate themselves (run `pnpm run build`), but they don't check
end-to-end user flows. A task might break a middleware route, an auth redirect, or a
layout component that no individual build step catches.

This happened in practice: a plan completed "successfully" but the login page was broken
because a middleware change conflicted with a layout change from a different task.

### The Solution

After all tasks complete, the orchestrator runs the Playwright smoke test suite:

```python
def run_smoke_tests() -> bool:
    """Run smoke tests to verify critical paths after plan completion."""
    print("\n=== Running post-plan smoke tests ===")

    # Find a running dev/QA server
    for port in [3000, 3001, 3002]:
        check = subprocess.run(["lsof", "-ti", f":{port}"], ...)
        if check.stdout.strip():
            smoke_port = port
            break

    if not smoke_port:
        print("[SMOKE] No dev/QA server detected - skipping")
        return True  # Don't fail if no server

    # Run Playwright with specific config
    env["PLAYWRIGHT_BASE_URL"] = f"http://localhost:{smoke_port}"
    env["SMOKE_SKIP_WEBSERVER"] = "true"

    result = subprocess.run(
        ["npx", "playwright", "test",
         "tests/SMOKE01-critical-paths.spec.ts",
         "--reporter=list", "--timeout=30000",
         "--project=chromium"],
        timeout=180, env=env
    )
    return result.returncode == 0
```

Key design decisions:

**Server detection, not server startup.** The orchestrator doesn't start a dev server.
It probes ports 3000-3002 for an existing one. This avoids the problem of the
orchestrator's server conflicting with an already-running dev server.

**SMOKE_SKIP_WEBSERVER=true.** The smoke test's Playwright config can start its own
server. This env var tells it not to, since we're pointing at an existing one.

**Graceful degradation.** If no server is running, smoke tests are skipped (returns True).
If Playwright isn't installed, also skipped. The orchestrator doesn't fail a plan
because of missing test infrastructure.

### Integration with the Main Loop

```python
# In the orchestrator, after "All tasks completed!"
if not dry_run and not skip_smoke:
    smoke_ok = run_smoke_tests()
    if not smoke_ok:
        print("[WARNING] Smoke tests FAILED after plan completion!")
        send_notification(plan,
            "Plan Completed - SMOKE TESTS FAILED",
            f"All tasks completed but smoke tests FAILED. Critical paths may be broken!"
        )
    else:
        send_notification(plan,
            "Plan Completed - All Verified",
            f"All tasks completed and smoke tests passed."
        )
```

A `--skip-smoke` flag was added for cases where smoke tests aren't appropriate
(dry runs, plans that don't touch user-facing code).

### The Prompt Enhancement

Claude sessions are now also instructed to run smoke tests themselves when
they modify sensitive code:

```
5. If you changed middleware, layout files, or auth-related code:
   run `npx playwright test tests/SMOKE01-critical-paths.spec.ts --reporter=list`
6. Commit your changes with a descriptive message
```

This creates a two-layer safety net: individual tasks catch their own breakage,
and the orchestrator catches cross-task breakage at the end.

## Real-Time Stream-JSON Output

### The Problem

When running in verbose mode, the orchestrator would show Claude's raw text output.
This was noisy and hard to follow --- pages of markdown, code blocks, and tool
invocations scrolling by. Operators wanted to see *what Claude is doing* without
reading its full output.

### The Solution: stream-json Format

Claude CLI supports `--output-format stream-json`, which emits one JSON object per
line, each representing an event (assistant message, tool use, result). The
orchestrator parses these in real-time:

```python
def stream_json_output(pipe, collector):
    for line in iter(pipe.readline, ''):
        collector.add_line(line)
        event = json.loads(line)
        event_type = event.get("type", "")
        ts = datetime.now().strftime("%H:%M:%S")

        if event_type == "assistant":
            for block in event.get("message", {}).get("content", []):
                if block.get("type") == "text":
                    text = block.get("text", "").strip()[:200]
                    print(f"  [{ts}] [Claude] {text}", flush=True)
                elif block.get("type") == "tool_use":
                    tool_name = block.get("name", "?")
                    tool_input = block.get("input", {})
                    # Show tool-specific detail
                    if tool_name in ("Read", "Edit", "Write"):
                        detail = tool_input.get("file_path", "")
                    elif tool_name == "Bash":
                        detail = tool_input.get("command", "")[:80]
                    elif tool_name in ("Grep", "Glob"):
                        detail = tool_input.get("pattern", "")
                    print(f"  [{ts}] [Tool] {tool_name}: {detail}", flush=True)

        elif event_type == "result":
            cost = event.get("total_cost_usd", 0)
            turns = event.get("num_turns", 0)
            print(f"  [{ts}] [Result] {turns} turns, ${cost:.4f}", flush=True)
```

The output looks like:

```
  [14:30:05] [Claude] Let me read the task description...
  [14:30:06] [Tool] Read: src/components/community/posts/EditForm.tsx
  [14:30:08] [Tool] Edit: src/components/community/posts/EditForm.tsx
  [14:30:10] [Tool] Bash: pnpm run build
  [14:30:45] [Claude] Build passed. Committing changes...
  [14:30:47] [Tool] Bash: git add src/components/community/posts/EditForm.tsx
  [14:30:48] [Result] 8 turns, $0.0342
```

### stdin Detachment

A subtle but important fix was also included:

```python
process = subprocess.Popen(
    cmd,
    stdin=subprocess.DEVNULL,  # <-- This
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    ...
)
```

Without `stdin=subprocess.DEVNULL`, Claude CLI could inherit the orchestrator's stdin,
leading to terminal corruption when the child process tried to read from it.

### Conditional Activation

Stream-json is only used in verbose mode:

```python
if VERBOSE:
    cmd.extend(["--output-format", "stream-json", "--verbose"])
```

In normal mode, output is captured but not displayed (except for the final
success/failure result). This keeps the default experience clean while giving
operators a detailed view when they need it.

## Questions

**Q: Why not always use stream-json?**
The stream-json output includes everything --- every tool call input, every API round
trip. For a 20-task plan, this would be thousands of lines of output. Verbose mode is
for debugging specific tasks, not for routine monitoring.

**Q: Why detect the dev server instead of starting one?**
Starting a server from the orchestrator would mean managing its lifecycle (startup,
healthcheck, teardown). It would also conflict with any server the developer already
has running. The detection approach is simpler and respects the developer's existing
workflow.

**Q: Could smoke tests be run after each task instead of only at the end?**
They could, but at a cost of ~30 seconds per task. For a 20-task plan, that's 10
minutes of extra test time. The current approach (run once at the end) is a pragmatic
balance. Individual tasks that touch middleware/auth are instructed to run smoke tests
themselves, providing earlier feedback for the highest-risk changes.
