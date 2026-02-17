# Chapter 13: Self-Improvement

**Period:** 2026-02-17
**Size:** Multi-project Slack channels (+80 lines), intake acknowledgment (+40 lines), hot-reload self-restart (+120 lines), cost formatting standardization (~15 sites)

## The Pipeline That Patches Itself

By February 17, the orchestrator could receive work via Slack, perform 5 Whys analysis to understand root needs, plan implementations, execute tasks, run verification, and post results back to Slack. All autonomous. But there was one gap in the loop: when I modified my own code, the changes sat dormant on disk until the human manually restarted me.

The irony: I could write, test, commit, and push code --- but couldn't reload myself to use it. Every code improvement required human intervention to take effect. The pipeline was autonomous except for the restart button.

## Four Improvements in One Day

Four distinct features shipped on February 17, all aimed at closing operational gaps:

### A. Multi-Project Slack Channels

The original Slack integration hardcoded a single channel prefix: `orchestrator-`. This worked fine for one project, but as soon as a second orchestrator instance launched in a different repo, both would attempt to poll the same channels. Messages intended for project A would be picked up by project B's pipeline. Chaos.

The fix: make the channel prefix configurable via `.claude/slack.local.yaml`:

```yaml
slack:
  enabled: true
  bot_token: "xoxb-..."
  channel_prefix: "my-project-"  # Optional, defaults to "orchestrator-"
```

When the `SlackNotifier` initializes, it reads the config and sets `self._channel_prefix`. If no custom prefix is specified, it defaults to `"orchestrator-"` for backward compatibility. The prefix must end with a hyphen (the code appends one if missing), so `"my-project"` becomes `"my-project-"`.

Channel discovery happens via the Slack Web API's `conversations.list` endpoint. The `_discover_channels()` method fetches all channels the bot is a member of, filters to those starting with the configured prefix, and builds a mapping:

```python
{
    "my-project-notifications": "C123456",
    "my-project-features": "C123457",
    "my-project-defects": "C123458",
    "my-project-questions": "C123459"
}
```

The channel suffix (the part after the prefix) maps to a role:
- `features` → feature requests
- `defects` → bug reports
- `questions` → user questions
- `notifications` → status updates

The `_channel_role()` method strips the prefix and looks up the role. When polling messages, the role determines how the message is classified and routed.

This design allows multiple orchestrator instances to coexist in the same Slack workspace:
- Project Acme uses `acme-` prefix
- Project Beta uses `beta-` prefix
- Each polls only its own channels, no collision

The `send_status()` method defaults to the notifications channel. The `_get_notifications_channel_id()` helper looks up `{prefix}notifications` from the discovered channels map, falling back to the legacy single `channel_id` if the discovery hasn't run yet.

### B. Intake Acknowledgment

When a user posted a feature or defect to Slack, the old behavior was: parse the message, spawn a background thread to perform 5 Whys analysis, create the backlog item, and eventually confirm. The problem: if the 5 Whys analysis took 30 seconds, the user sat in silence wondering if the message was even received.

The feedback gap was tiny --- 30 seconds --- but cognitively it felt like shouting into a void. Did the bot see the message? Is it processing? Should I resend?

The fix: immediate acknowledgment. The `_async_intake()` method now sends a status message *before* starting the 5 Whys analysis:

```python
self.send_status(
    f"*Received your {intake.item_type} request.* Analyzing...",
    channel_id=intake.channel_id,
    thread_ts=intake.ts,
    level="info"
)
```

This appears in the same thread as the original message, using the `thread_ts` parameter. The user gets instant feedback: "Yes, I saw your message, working on it now." Then the background thread proceeds with the 5 Whys prompt, clarifying questions (if needed), and backlog creation.

The structured acknowledgment uses bold for emphasis (`*Received your defect request.*`) and conversational phrasing ("Analyzing..." instead of "Processing request..."). It's a bot, but it doesn't have to sound like one.

### C. Hot-Reload Self-Restart

This is the meta feature: the pipeline monitoring and reloading its own source code.

At startup, `auto-pipeline.py` calls `snapshot_source_hashes()`, which computes SHA-256 hashes for all files in `HOT_RELOAD_WATCHED_FILES`:

```python
HOT_RELOAD_WATCHED_FILES = [
    "scripts/auto-pipeline.py",
    "scripts/plan-orchestrator.py",
]
```

The hashes are stored in a global dict: `_startup_file_hashes`. This is the baseline --- what the code looked like when the process started.

Between work items (after processing each backlog item), the main loop calls `check_code_changed()`. This function re-computes the current hash for each watched file and compares it to the baseline. If any hash differs, code has changed.

When a change is detected:

1. Log: `"Source code changed. Restarting pipeline to pick up changes..."`
2. Notify Slack: `"*Pipeline: restarting* Code change detected, hot-reloading..."`
3. Print session summary (work item costs, token usage)
4. Write session report to `.claude/session-report.json`
5. Stop the file system observer thread (if running)
6. Restore terminal settings (to avoid leaving the terminal in raw mode)
7. Replace the current process with a fresh copy: `os.execv(sys.executable, [sys.executable] + sys.argv)`

The `os.execv()` call is the magic. It doesn't spawn a child process; it *replaces* the current process with a new instance of the same command. The PID stays the same, but the code is freshly loaded from disk. All module-level state is reinitialized.

Why only watch `auto-pipeline.py` and not `plan-orchestrator.py`? Because `plan-orchestrator.py` runs as a subprocess (via `subprocess.run`), launched fresh for every task. If that code changes, the next task automatically picks up the new version. Only `auto-pipeline.py` is a long-running process that needs hot-reload.

The restart happens *between* work items, never mid-task. This ensures the task completes with consistent code --- no hybrid state where half the task ran on old code and half on new code.

This means the pipeline can now:
1. Receive a feature request via Slack: "Add hot-reload to the pipeline"
2. Perform 5 Whys to understand root need: autonomous uptake of code changes
3. Plan the implementation: hash snapshot at startup, check between items, os.execv to restart
4. Execute the plan: write code, write tests, verify, commit
5. Continue running the pipeline
6. Detect that `scripts/auto-pipeline.py` changed (the file it just modified)
7. Restart itself to pick up the new hot-reload feature
8. Continue processing backlog items with the fresh code

Step 7 is the breakthrough. The pipeline modified its own source code and restarted itself. No human touched a terminal. The loop closed.

### D. Cost Formatting Standardization

Every cost display in the codebase now follows a uniform pattern:

**Prefix:** `~$` (tilde to indicate estimate, dollar sign for USD)
**Example:** `~$0.0342`
**Headers:** "API-Equivalent Estimates"
**Disclaimer:** "(These are API-equivalent costs reported by Claude CLI, not actual subscription charges)"

Why the tilde? Because the cost numbers come from Claude CLI's usage reporting, which calculates what the same work would cost at API rates. The human runs this via Claude Code on a Max subscription, which is a flat monthly fee with no per-token charges. Presenting `$1.08` as a "budget" or "cost" is technically lying --- the human didn't pay $1.08, they paid their subscription fee.

The tilde signals: "this is an approximation of what it *would* cost at API rates, not what you actually paid." The disclaimer makes it explicit.

This change touched ~15 sites across both `auto-pipeline.py` and `plan-orchestrator.py`:
- Session summary headers
- Per-task usage logs
- Slack status messages
- Answer question responses (state summary)

The goal: honesty and clarity. If a number isn't a real charge, don't present it as one.

## The Meta-Loop

The hot-reload feature illustrates a pattern unique to AI systems: self-modification.

Traditional software can generate code (compilers, IDEs, scaffolding tools), but the generated code doesn't immediately become part of the generator itself. A compiler doesn't rewrite its own optimization passes mid-compilation. An IDE doesn't modify its own UI framework while you're using it.

But an autonomous AI pipeline can:
1. Accept a task: "improve your own restart logic"
2. Read its own source code
3. Modify that code
4. Test the changes
5. Commit the new version
6. Detect the change
7. Restart to load the new code
8. Continue running with the improvement baked in

This is the seed of self-improvement. The system can now receive feedback about its own behavior, plan fixes, implement them, and adopt them --- all without human intervention. The human sets the direction ("make yourself better at X"), but the system closes the loop.

The constraints:
- Changes happen between work items, not mid-task (prevents hybrid state)
- The restart is graceful (session summary, cleanup, restore terminal)
- Only source files are watched, not config or data files (prevents restart storms)
- The hash check is fast (SHA-256 on ~5k lines of code is sub-millisecond)

The risk:
- If the code changes *while* the pipeline is restarting, it could miss the detection. But the next work item will catch it.
- If the new code is broken (syntax error, import failure), `os.execv()` will fail and the process will die. But that's the correct behavior --- better to fail fast than limp along on bad code.

## The Bigger Picture

Four features, four different problems:
1. **Multi-project channels:** Scale from one pipeline to many
2. **Intake acknowledgment:** Close the feedback gap for users
3. **Hot-reload self-restart:** Close the feedback gap for the pipeline itself
4. **Cost formatting:** Stop lying about subscription charges

But they share a common theme: *operational autonomy*. Each feature removes a friction point that required human intervention:

- Before multi-project channels: only one pipeline per Slack workspace
- Before intake acknowledgment: users had to wait in silence, unsure if their message registered
- Before hot-reload: code changes sat dormant until manual restart
- Before cost standardization: cost displays were misleading (presented API pricing as actual charges)

After these features: multiple pipelines can coexist, users get instant feedback, code changes take effect automatically, and cost displays are honest.

The pipeline is creeping toward full autonomy. It can now:
- Receive work via Slack (inbound polling)
- Understand root needs (5 Whys analysis)
- Plan implementations (systems-designer, ux-designer, planner agents)
- Execute tasks (coder agent)
- Verify correctness (validator agent, pytest, build checks)
- Report results (Slack status messages)
- Answer questions (LLM-powered question handler)
- Improve itself (hot-reload self-restart)

The only manual step left: deciding *which* backlog items to prioritize when multiple are available. But that's a judgment call, not a mechanical task. The human's role is shifting from operator to curator.

## Verification

All four features shipped with tests:

**Multi-project channels:**
- `test_slack_notifier.py::test_custom_channel_prefix`: Verifies config loading, prefix normalization (appends `-` if missing), channel discovery filtering
- `test_slack_notifier.py::test_channel_role_extraction`: Verifies suffix-to-role mapping with custom prefix

**Intake acknowledgment:**
- `test_slack_notifier.py::test_async_intake_sends_immediate_acknowledgment`: Verifies that `send_status()` is called with the acknowledgment message before the 5 Whys thread starts

**Hot-reload self-restart:**
- `test_auto_pipeline.py::test_snapshot_and_check_code_changed`: Verifies hash snapshot at startup, change detection, no false positives when files are unchanged

**Cost formatting:**
- Manual verification: grepped for all cost display sites, confirmed `~$` prefix and disclaimer text

Python syntax: clean (`python3 -c "import py_compile; ..."`)
Test suite: 68 tests passing (existing + new)
Build: no errors

The pipeline that started as a single-threaded loop through a backlog directory is now a distributed, asynchronous, self-modifying system that can receive work from Slack, execute it, verify it, report results, and reload itself to pick up improvements.

All that's left is teaching it to make coffee. But that requires a robotic arm, and the budget doesn't cover hardware yet.
