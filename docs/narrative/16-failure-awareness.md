# Chapter 16: Failure Awareness

**Period:** 2026-02-20 to 2026-02-24
**Size:** ~30 lines in `plan-orchestrator.py` (deadlock detection, permission flags), ~50 lines in `auto-pipeline.py` (deadlock guard, permission flags, completion summary extractor), documentation updates to README.md, docs/setup-guide.md, and six completed backlog items across three defects and three features

## The Sandbox Didn't Know About Itself

When the sandbox feature shipped, it passed `--allowedTools` to the Claude CLI. That flag
controls which tools are available. But the CLI has two separate axes for this:

1. **Tool availability** (`--allowedTools`) --- which tools can be invoked at all
2. **Approval behavior** (`--permission-mode`) --- whether each invocation requires
   interactive confirmation before proceeding

The non-sandbox path uses `--dangerously-skip-permissions`, which suppresses all approval
prompts in one shot. This masks the two-axis model entirely. The sandbox path was written
by analogy: pass `--allowedTools` to restrict the tool list, done. Nobody asked whether
the approval behavior also needed configuring.

The answer was: yes, it did. With `--permission-mode` unset, the CLI defaults to
`"default"`, which prompts the user before each Write or Edit call. In a headless
subprocess launched with `stdin=subprocess.DEVNULL`, that prompt has nowhere to go. The
process waits. The timeout fires. The task dies.

The fix was two lines in each of `build_permission_flags()` in `plan-orchestrator.py`
and `auto-pipeline.py`:

```python
flags += ["--permission-mode", "acceptEdits"]
```

`acceptEdits` allows Write and Edit without prompting while still requiring approval for
other sensitive operations --- the correct middle ground for a sandboxed coder. The two
axes exist for a reason, and the sandbox now handles both.

What makes this a failure-awareness story: the system did not understand its own
permission model. It had implemented one axis and silently ignored the other. The bug was
invisible during manual testing because the human always approves prompts. It only
manifested in the headless path, where no approval is possible.

## The Loop That Didn't Know It Was a Loop

Chapter 15 described a pipeline that cycled every three seconds because an archive
function forgot to delete the source file. That was a loop the system could eventually
escape --- the archive function was fixable.

This one was different. The scenario: a task fails mid-plan. Other tasks depend on it.
Those dependents can never run. The plan has pending tasks, so the orchestrator considers
it in progress. The orchestrator runs, calls `find_next_task()`, gets `None` back, and
concludes "All tasks completed!" The plan was treated as done. The pipeline archived it.

Except: "All tasks completed" and "no runnable task exists" are not the same thing.
`find_next_task()` returned `None` in both cases, and the orchestrator couldn't tell
them apart.

The 5 Whys traced the root cause to an absent state machine. Each component ---
`find_next_task`, `is_plan_fully_completed`, `find_in_progress_plans` --- made narrow
local decisions. No component owned the question: "Is this plan permanently stuck?" That
question requires a global view of the plan's task graph, which none of them had.

`detect_plan_deadlock()` at line 2039 of `plan-orchestrator.py` is the function that
now owns that question. It inspects all non-terminal tasks (pending and in_progress),
follows their dependency edges, and asks: is every one of them transitively blocked by
a failed or suspended task? If yes, the plan is deadlocked.

When the orchestrator's main loop calls `find_next_task()` and gets `None` back, it now
calls `detect_plan_deadlock()`. If deadlock is confirmed, it:

1. Sets `meta.status: failed` in the YAML and writes the file
2. Commits the state to git so the next session starts from a clean record
3. Sends a Slack error notification with the list of blocked tasks
4. Exits with `sys.exit(1)` so the pipeline knows something went wrong

The pipeline's `find_in_progress_plans()` guards the other end: any plan with
`meta.status == "failed"` is skipped entirely. No re-spawning. No infinite loop. The
plan is stuck; the system acknowledges that and moves on to the next item.

## The Permission That Crossed a Border

The sandbox fix and the deadlock fix were both self-contained: one codebase, one bug,
one fix. The third defect was trickier because the symptom appeared in a different
project.

The Cheapoville pipeline reported that its orchestrator was failing to execute coder
tasks. The agent kept hitting permission errors on Write and Edit. The session logs showed
the task being classified as `code-reviewer` instead of `coder`, which gave it the
READ_ONLY permission profile: Read, Grep, Glob, Bash only. No writing allowed.

The classification came from `infer_agent_for_task()`, which matched task descriptions
against keyword lists to guess the appropriate agent. The `REVIEWER_KEYWORDS` list
contained:

```python
REVIEWER_KEYWORDS = ["verify", "review", "check", "validate", "regression", "compliance"]
```

These are single words, and they appear constantly in implementation task descriptions.
"Add content moderation **check** functionality" matched "check." "Implement **review**
UI for moderators" matched "review." Any task mentioning validation, verification, or
compliance review got classified as a code reviewer and silently lost its write access.

The other specialist keyword lists --- planner, qa-auditor, spec-verifier --- all used
multi-word phrases: "generate test plan," "spec compliance," "UX review pass." Those are
specific enough to avoid false positives. `REVIEWER_KEYWORDS` and `DESIGNER_KEYWORDS`
were the exception, and the Cheapoville pipeline was the first consumer to hit it at
scale.

The fix replaced every single-word entry with multi-word phrases:

```python
REVIEWER_KEYWORDS = [
    "code review", "review code", "review implementation",
    "review changes", "verify implementation", "verify changes",
    "run verification", "check compliance", "compliance check",
    "regression test", "regression check",
]
```

A task named "Run verification suite" still routes to code-reviewer. A task named
"Implement verification middleware" routes to coder. The distinction is in the phrase,
not the word.

The broader lesson: permission inheritance is not just a deployment problem. When a
consumer project picks up a new version of the orchestrator, it inherits the keyword
logic along with everything else. A subtle misclassification bug becomes a systemic
permission bug for every consumer simultaneously. Shared infrastructure carries shared
failure modes.

## Explaining What Went Wrong

The first three items are about the system failing to understand itself. The next three
are about the system learning to communicate what it knows.

When the pipeline archives a completed defect, the original Slack notification contained
only the item name and duration:

```
Pipeline: completed defect: 7-pipeline-agent-commits-unrelated-working-tree-changes
Duration: 14m 32s
```

This is technically accurate. It is also useless for triage. The human reading the
notification channel had no way to know whether this fix was a one-line guard or a
deep rearchitecting, whether it touched shared code or was isolated, whether it warranted
a manual review or could be trusted. That judgment required opening the backlog file.

`_extract_completion_summary()` in `auto-pipeline.py` reads the completed item's
markdown file before the archive move and extracts a 2-3 sentence summary. The extraction
follows a priority chain:

1. `## Root Cause` section first sentence --- most explicit statement of what was wrong
2. `**Root Need:**` line from the 5 Whys analysis --- second choice
3. `## Summary` section first sentence --- fallback

For the fix side, it looks for the last verification log entry that mentions "fix" or
"commit" to find what changed. The result is appended to both the notifications channel
and the type-specific channel messages:

```
Pipeline: completed defect: 7-pipeline-agent-commits-unrelated-working-tree-changes
Duration: 14m 32s
Root cause: Pipeline commits all staged changes, not just its own. Fix: added git stash
before task execution and pop after, scoped to task-owned changes only.
```

The function extracts from structured markdown rather than calling an LLM to summarize.
No API call, no latency, no cost. The 5 Whys intake process and the verification logs
already produce concise human-readable content in predictable sections. The extraction
is regex over structure, not inference over prose.

The principle: the data was already there. The system just wasn't surfacing it.

## Making the Tacit Explicit

The final two items are documentation. Neither added code. Both added knowledge.

**Cross-project Slack reporting** was working --- MIQ-Orchestrator had been using the
channels to submit defects --- but the README's "Cross-Instance Collaboration" section
explained the architecture without explaining the setup. A downstream operator reading
it would understand that cross-project reporting was possible but have no path to
reproduce it. Three pieces of tacit knowledge were missing:

1. How upstream channel names are structured (prefix-based, configurable)
2. How to invite the consumer bot to the upstream channels (Slack `/invite` command,
   required scopes)
3. How message routing works once the bot is in the channel (channel_prefix in config,
   identity protocol preventing self-loops)

The new "Setting Up Cross-Project Reporting" section in the README and the corresponding
walkthrough in `docs/setup-guide.md` give a downstream operator a complete procedure
to follow without needing to read the source.

**Single-command onboarding** addressed a different gap. The `setup-slack.py` script
already supported `--bot-token`, `--app-token`, `--prefix`, and `--non-interactive` flags
for adding the orchestrator to a second project that reuses an existing Slack app. The
command worked. It just wasn't discoverable. A cross-project adopter who already had a
Slack app running in one project would read the setup guide, see "Set up Slack" as step
3, and conclude they needed to go through the first-time browser-based setup again.

The fix was a prominent "Adding a Second Project to an Existing Workspace" subsection in
both the README and setup guide, with a copy-pasteable one-liner:

```bash
python3 scripts/setup-slack.py \
  --prefix myproject \
  --bot-token xoxb-... \
  --app-token xapp-... \
  --non-interactive
```

No browser required. The command creates the prefix-scoped channels, writes
`orchestrator-config.yaml`, and exits. The existing knowledge was already encoded in the
script. The documentation made it visible.

## What Failure Awareness Means

Six items, three defects and three features. The connecting thread is not the bug class
or the feature domain. It is a posture: understanding what can go wrong, detecting it
when it does, and communicating it clearly.

The sandbox bug was a failure the system could not detect because it had never modeled
its own two-axis permission structure. The deadlock bug was a failure the system could
not detect because no component had a view of the full task graph. The keyword
misclassification was a failure the system could not detect because it was silent ---
the wrong agent ran, got permission errors, failed, and the plan moved on.

Each fix gave the system more knowledge about itself: that permissions have two
independent axes, that "no runnable task" is not the same as "plan complete," that
keyword specificity determines downstream access. The system did not become smarter.
It became more aware of the ways it was already failing.

The notification feature is a different kind of awareness. Not "know your own failure
modes" but "say what went wrong without being asked." The root cause and fix summary
turns a completion event into a legible record. The human reading the channel does not
need to reconstruct what happened. The system explains itself.

The documentation items formalize both kinds of awareness. Tacit operational knowledge
--- how cross-project channels are set up, how a second-project onboarding works ---
becomes explicit and reproducible. The system's behavior and its documentation converge
toward the same model.

## Verification

- `build_permission_flags()` in both scripts includes `["--permission-mode", "acceptEdits"]` when sandbox enabled
- Sandbox permission tests updated in `test_plan_orchestrator.py` and `test_auto_pipeline.py`
- `detect_plan_deadlock()` at line 2039 of `plan-orchestrator.py` correctly identifies unreachable pending tasks
- Orchestrator sets `meta.status: failed`, commits, sends Slack error, exits non-zero on deadlock
- `find_in_progress_plans()` in auto-pipeline skips plans with `meta.status == "failed"`
- 11 deadlock-specific unit tests pass; 3 pipeline deadlock tests pass
- `REVIEWER_KEYWORDS` and `DESIGNER_KEYWORDS` replaced with multi-word phrases
- False-positive regression tests pass: "check", "review", "validate" in implementation contexts infer "coder"
- `_extract_completion_summary()` extracts root cause and fix from markdown sections
- Extraction is called before `archive_item()` while the source file is still at its original path
- Summary appended to notifications and type-specific channel Slack messages
- README.md and docs/setup-guide.md updated with cross-project reporting setup walkthrough
- README.md and docs/setup-guide.md updated with single-command onboarding section
- All tests pass (374 passed across the period)
