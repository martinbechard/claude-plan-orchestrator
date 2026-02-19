# Chapter 14: Cognitive Specialization

**Period:** 2026-02-18
**Size:** `SLACK_LLM_MODEL` constant + 3 call sites, `planner.md` → opus (pending), `ux-designer.md` → opus + loop pattern (pending), new `ux-implementer.md` agent (pending), feature backlog item #9

## The Question Nobody Had Asked

The pipeline had eleven agents. Each one was assigned a model. Most of them were assigned sonnet. Nobody had ever asked why.

The model field in an agent's frontmatter is easy to write and easy to ignore. You set it once, move on, and the agent runs forever on whatever you put there. Sonnet is a reasonable default: capable, fast, affordable. So sonnet it was, for almost every agent, with no particular deliberation.

The catalyst for re-examining this was a seemingly unrelated question: should a UX designer agent be running on the same model as a code reviewer? They're both "agents." They both get a system prompt and a task. But their jobs couldn't be more different.

A code reviewer follows a checklist. The rules are explicit, the verdict is structured, and the output is deterministic given the input. PASS, WARN, or FAIL, with file:line references. There's no ambiguity in the task, no creative latitude, and no cascading consequence if the model misses a nuance --- the coder agent will fix whatever the reviewer flags and the reviewer will run again.

A UX designer starts from a vague human need and produces a design that will govern every implementation decision downstream. The output is open-ended, the stakes are high, and a shallow or misaligned design compounds through every subsequent task. Get the design wrong and you don't just have a bad design --- you have six tasks of implementation that built the wrong thing.

These are not the same job. They shouldn't use the same model.

## The Audit

A systematic review of all eleven agents, plus the three internal LLM calls the orchestrator makes for Slack, produced a clearer picture of what each agent actually does:

**Structured verification agents** --- code-reviewer, validator, issue-verifier, spec-verifier, ux-reviewer --- all follow explicit checklists with clear pass/fail criteria. The task is defined, the rules are enumerated, and correctness is checkable against those rules. Sonnet handles this well. These agents don't need to reason from first principles; they need to apply principles consistently.

**Creative generation agents** --- ux-designer, systems-designer --- start from ambiguity and produce output that cascades into everything that follows. Systems-designer was already on opus (correctly), but ux-designer was on sonnet. The UX designer performs a 5 Whys analysis from scratch, invents wireframes, reasons about accessibility, and designs interaction patterns for states the spec never mentioned. That's not checklist work.

**Orchestration agents** --- planner, coder, frontend-coder, qa-auditor --- sit in the middle. Planner was the most interesting case: it reads a winning design and translates it into a YAML task graph. The design is already specified, but decomposing it into session-sized tasks with correct dependencies and the right agent assignments requires genuine judgment. A bad plan doesn't just produce a bad task --- it produces six bad tasks, each one building on the previous mistake. The cascade multiplier is the key insight: agents whose errors compound downstream warrant more reasoning capacity than agents whose errors are caught and corrected locally.

**Internal Slack calls** --- the orchestrator makes three substantive LLM calls for Slack interactions: answering questions from the human, performing 5 Whys intake analysis on new submissions, and retrying incomplete analyses. These calls run on whatever model is passed to `_call_claude_print()`. The default was sonnet, inherited from the function signature. But answering a human's question about pipeline state requires judgment, context synthesis, and conversational quality. The intake analysis produces the root-need framing that governs how a feature is understood for its entire lifecycle. These aren't checklist tasks either.

The result: three changes.

`SLACK_LLM_MODEL = "claude-opus-4-6"` --- a named constant, positioned next to the other Slack constants, pinning all substantive Slack LLM calls to the exact model version. Message routing (classifying inbound messages as feature/defect/question/none) stays on haiku: it's a classification task, not a reasoning task, and it runs on every inbound message.

`systems-designer` already ran on opus. `planner` and `ux-designer` both needed to move there. Planner for the cascade reason. UX designer for a more interesting reason that required a separate architectural decision.

## The Loop

The human observation: Sonnet is actually quite good at visual and interaction design. The problem with running the UX designer purely on Sonnet isn't the design quality --- it's the requirements analysis. Sonnet given a vague brief tends to make assumptions silently. Opus given the same brief tends to notice that the brief is vague and reason about what it's actually asking for.

What if they worked together?

The proposed pattern: Opus acts as the stateful orchestrator of the design task. It reads the requirements, performs the 5 Whys analysis, produces a detailed brief, then invokes Sonnet as a subagent to realize the design. Sonnet, working from a precise brief, does what it does well: generate wireframes, define component specs, sketch responsive breakpoints, reason through interaction states. When Sonnet finishes, it returns one of two things: a complete design document, or a structured question.

```
STATUS: QUESTION
QUESTION: The spec mentions a "settings panel" but doesn't define what settings
it contains. Should this match the user account settings at /account, or is
this a different set of controls specific to this feature?

--- or ---

STATUS: COMPLETE
[full design document follows]
```

The rigid status envelope is essential. Opus needs to parse the output programmatically, and natural language boundaries between "here's my design" and "I have a question" are unreliable. The structured format makes it unambiguous.

When Opus receives a question, it doesn't pass it to the user --- it answers it using its own reasoning about the codebase context and the 5 Whys root need it already derived. Then it invokes Sonnet again, this time with the full accumulated Q&A context injected into the prompt. This is the crucial constraint: Sonnet has no memory between invocations. Each call is a fresh session. Opus is the only party with continuity. The Q&A history isn't just useful context for the next invocation --- it's mandatory. Sonnet will ask the same question again if it isn't told the answer was already resolved.

The loop continues until Sonnet returns a complete design or a cap is reached (three rounds, to prevent cost runaway). If the cap is hit, Opus documents the unresolved questions in the design output and produces a best-effort design based on the answers it could derive independently. The human sees the open questions in the design document and can decide whether they matter before implementation begins.

## The Agent Teams Detour

The pattern described above uses subagents: Opus spawns Sonnet as a child, Sonnet returns a result, Opus reads it and decides what to do next. This is the standard subagent model.

The human, knowing that Anthropic had shipped something called "agent teams," asked whether the interaction could be more direct: Sonnet working on the design, asking questions back to Opus in real time, Opus answering and letting Sonnet continue. True bi-directional conversation between models at different capability tiers.

Agent teams do exist and they do support this. In the agent teams architecture, each teammate is a fully independent Claude Code session with its own context window. Teammates communicate through a shared mailbox: any teammate can send a message directly to any other, the recipient receives it asynchronously, and replies flow back the same way. A Sonnet teammate mid-design could send "I need to know whether the settings panel should match the account settings at /account" directly to the Opus lead, the Opus lead could reply "yes, reuse the same component structure," and Sonnet would receive that answer and continue --- all without losing the design context it had built up.

This is a genuine capability advantage over the subagent model. Subagents can only report results back to the parent. There is no channel for a child to ask a question and receive an answer mid-execution. If a subagent hits an ambiguity, its only options are to guess, to fail, or to return a partial result that the parent interprets as a question and uses to construct a new invocation. The session that held the in-progress design is gone; the next Sonnet invocation starts fresh.

The trade-offs, however, are substantial:

**Token cost scales with team size.** Every teammate is a running Claude Code session with its own context accumulation. An Opus lead plus a Sonnet teammate means two separate API-equivalent cost streams, with all the overhead of session initialization, context loading, and inter-session messaging. For a single design task, this overhead is hard to justify.

**Agent teams are experimental and disabled by default.** They require `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` in settings. The documentation explicitly calls out known limitations: session resumption doesn't restore in-process teammates, task status can lag (blocking dependent work), and the lead cannot be changed mid-session. Running experimental infrastructure in a production pipeline that executes backlog items autonomously overnight is a meaningful risk.

**The sequential nature of design negates the primary benefit.** Agent teams earn their overhead when workers can operate in parallel --- competing hypotheses, simultaneous module implementations, parallel code review across different domains. Opus analyzing requirements _must_ complete before Sonnet can design. Sonnet's design _must_ complete before implementation begins. There is no work to parallelize, so the inter-agent communication channel is the only benefit on offer, and that benefit is specific to the mid-task Q&A case.

**Visibility and recoverability are degraded.** In the YAML-plan model, every agent invocation is a tracked task with status, attempt count, and result message. The orchestrator knows what happened, when, and why. An agent team's internal exchanges are opaque to the orchestrator --- if Sonnet runs into trouble mid-design and the team enters an inconsistent state, the YAML plan has no record of it. Recovery requires understanding the team's internal state, not just re-running the task from the last known-good checkpoint.

The subagent loop achieves the same Q&A quality through a different mechanism: instead of letting Sonnet ask questions in real time, Opus invests upfront in a brief thorough enough that the questions don't arise. After pre-emptive clarification rounds --- Opus reasoning from the 5 Whys root need, the codebase context, and any prior Q&A --- Sonnet receives a brief that anticipates the ambiguities and resolves them before work starts. The output includes not just the design document but a record of every assumption surfaced and resolved. When implementation begins, the coder agent has context that the original spec never contained.

The choice comes down to where the intelligence is applied: agent teams apply it reactively (Sonnet discovers an ambiguity and asks mid-execution), the subagent loop applies it proactively (Opus anticipates ambiguities and resolves them in the brief before Sonnet starts). For a system built around fresh-session isolation and file-based state handoffs, proactive clarification fits the architecture. Reactive clarification requires a communication substrate the orchestrator doesn't currently provide --- and that's worth building, eventually, but not before the simpler pattern has been validated.

## The Suspension Problem

There's a case the loop can't handle: when Opus can't answer Sonnet's question from first principles because the answer depends on a human decision that genuinely hasn't been made yet. What color palette should the dashboard use? What should the empty state illustration look like? Should this feature be gated behind a premium tier?

The pipeline has no way to ask the human interactively. Agents run headless via `claude --print`, which is non-interactive by design. `AskUserQuestion` doesn't reach the human in this context.

The Slack channel exists, and the human already monitors it. But wiring "Opus receives an unanswerable question and needs to pause the work item" into the current pipeline requires changes that go well beyond the UX designer agent:

The work item needs a new state: **suspended**. Not failed (which triggers retries), not completed (which archives it), but parked --- excluded from normal processing while awaiting a response. The auto-pipeline's main loop currently has no concept of suspension; it processes items or skips them.

The question needs to be posted to the features or defects Slack channel, not the questions channel. The human monitors the features/defects channels for completion confirmations. A question posted there will be seen in the same context as the work it belongs to. The question must include enough context --- which item, which design, exactly what is being asked --- for the human to understand without having to look up the original spec.

The answer needs to be correlated back to the suspended item. Slack threads are the natural mechanism: the question is posted as a new message, the human replies in the thread, and the bot knows that replies to that specific message belong to that specific item. Alternatively, the question can embed a structured ID (slug + timestamp) that the human's reply must reference. Either way, the correlation challenge is real and non-trivial.

When the answer arrives, the item must be reinstated. Not restarted from scratch --- the design work that was done before the question is valuable and shouldn't be discarded. The answer must be injected as additional context into the Opus session that resumes the loop.

This is a meaningful feature, not a small patch. It touches the work item state machine, the Slack inbound handler, the auto-pipeline main loop, and the UX designer agent's protocol for signaling an unanswerable question. It goes into the backlog as feature #9, clearly scoped, with the key design challenges documented.

For now: Opus answers questions with its own reasoning, documents its assumptions, and produces a best-effort design. The human reviews the open-questions section before implementation starts if they want to catch anything Opus got wrong.

## What This Actually Is

The model selection audit, the Opus/Sonnet loop, and the suspension concept share an underlying theme: the pipeline is starting to treat cognition as a resource to be allocated, not a uniform capability to be applied uniformly.

Every task isn't the same. A code reviewer and a UX designer are doing categorically different cognitive work, and treating them identically --- same model, same prompt structure, same handoff protocol --- is a form of false economy. It's cheap in the short term and expensive in the long term, because quality problems in design agents compound through implementation in ways that quality problems in verification agents don't.

The Opus/Sonnet loop takes this further: it recognizes that even within a single task, different phases of the work have different cognitive profiles. Requirements analysis requires depth. Design realization benefits from breadth and creative fluency. Using the same model for both is like using the same tool for all phases of construction because buying two tools costs more upfront.

And the suspension feature, if and when it ships, would represent something more interesting still: the pipeline pausing its own work because it knows what it doesn't know, and routing its uncertainty to the right authority rather than either guessing or failing. That's a form of epistemic honesty most systems never develop --- the ability to distinguish between "I can figure this out" and "I need a human to decide this."

The pipeline is developing judgment about the limits of its own judgment. That's not a small thing.

## Verification

- `SLACK_LLM_MODEL = "claude-opus-4-6"` added to `plan-orchestrator.py` constants block; three `_call_claude_print()` call sites updated; syntax clean
- `plugin.json` bumped to `1.1.0`; `RELEASE-NOTES.md` created
- `CLAUDE.md` created with versioning instruction
- Feature backlog #9 added to `docs/feature-backlog/`
- Agent model changes (`planner` → opus, `ux-designer` → opus + loop pattern, new `ux-implementer`) pending implementation
