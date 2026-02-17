# Chapter 12: Talking Back

**Period:** 2026-02-16
**Size:** +250 lines to `scripts/plan-orchestrator.py`, +500 lines to `tests/test_slack_notifier.py`, 2 agent markdown files updated

## The Question That Wasn't Answered

The orchestrator's Slack integration shipped in two waves: Feature #14 (Slack App Migration)
gave it a voice --- the ability to send status updates, defect reports, and idea suggestions
to Slack channels. Feature #15 (Inbound Message Polling) gave it ears --- the ability to
receive messages from the human and classify them as features, defects, questions, or control
commands.

But when a question arrived in `#orchestrator-questions`, the response was a polite brush-off:

```
Question received: what is the status?
Detailed answers are not yet available via Slack.
Check the terminal session for full pipeline context.
```

The irony: the orchestrator could detect that a question had been asked, classify it correctly,
and route it to the right handler. It just didn't think *actually answering* was part of the
original request. The inbound polling feature spec said "answer questions" and the
implementation said "acknowledge questions." The surface request was delivered; the root need
was not.

## A 5 Whys Analysis of Our Own Oversight

This gap became the catalyst for applying the very technique we then added to the codebase.
A 5 Whys analysis of the human's request to "send questions to the orchestrator via Slack":

1. **Why does the user want this?** To ask the pipeline questions from Slack.
2. **Why do they need that?** Because the terminal isn't always visible.
3. **Why is that important?** They want to oversee the pipeline without context-switching.
4. **Why does that matter?** Actionable information should arrive where the user already is.
5. **Why is that critical now?** The pipeline runs autonomously for hours; the human needs
   a lightweight way to check on it without interrupting the workflow.

**Root need:** Actionable pipeline state delivered in Slack, so the human can oversee the
pipeline from wherever they are.

The stub answer_question() was a textbook case of solving the surface request
("acknowledge the question") instead of the root need ("provide the actual answer").

## Three Changes

### A. LLM-Powered Answers

The pipeline's state is scattered across files: YAML plans track task progress,
`task-status.json` records the last completed task, backlog directories hold pending items,
completed-backlog tracks shipped work, and session logs capture cost data. All of this was
already on disk --- nobody was reading it for questions.

The first attempt used keyword matching and rigid Slack mrkdwn formatting. The human asked
"hi do you have any work right now?" and got a data dump of every section. They asked
"how did you calculate the cost?" and got the cost number repeated back at them. And the
cost number was API-equivalent pricing from Claude CLI --- meaningless for a Max subscription
user, presented without context as a "Budget."

The keyword matcher was cheap but awful. The human had asked for LLM-powered answers from
the start. The fix: `answer_question()` now gathers state from all five disk sources,
formats it as plain-text context, and passes it along with the question to Claude (haiku
model) via `run_claude_task()`. The LLM knows it's answering a Max subscription user, knows
the cost data is API-equivalent, and gives a natural conversational response. If the LLM
call fails, it falls back to sending the raw state with a disclaimer.

### B. Teaching the Design Agents

The systems-designer and ux-designer agents each received a new checklist step: perform a
5 Whys Analysis before starting any design. Surface request to root need, five levels deep.
If the root need diverges from the literal request, design for the root need and document
the divergence. The design output structure now starts with the 5 Whys Analysis section,
before the Architecture Overview or User Flow.

### C. Async Intake with 5 Whys for New Submissions

When a feature or defect arrives in Slack, the old behavior was immediate: parse the first
line as title, everything else as body, create a markdown file, confirm. Quick, but shallow.
The request might say "app crashes sometimes" when the root need is "stability under
concurrent load on Chrome."

The new intake system spawns a background thread that calls Claude (haiku model, for cost)
with a 5 Whys prompt. If the request is clear, it creates an enriched backlog item with the
analysis baked in. If unclear, it posts up to three clarifying questions back to the Slack
channel and waits for answers (up to 30 minutes). The answer routing happens through the
existing `process_inbound()` polling loop --- when a message arrives in a channel with a
pending intake, it gets routed to the waiting thread via a `threading.Event`.

The main pipeline loop never blocks. The intake thread is a daemon that dies quietly if the
process exits.

## The Immediate Field Test

The first implementation used keyword matching instead of an LLM. It was cheap but useless.
The human called it "terrible" and "awful" --- accurately. Three problems:

1. **"hi do you have any work right now?"** fell through to "summary" and dumped every data
   section. The human wanted a focused conversational answer, not a dashboard.

2. **"Last session: $1.08"** was presented as "Budget" with no context. The $1.08 is what
   the work would cost at API rates, reported by Claude CLI. The human is on a Max
   subscription --- they don't pay per-token. Presenting API pricing as a budget is lying.

3. **"how did you calculate the cost?"** repeated the cost number. The keyword matcher saw
   "cost" and re-dumped the data. It couldn't distinguish "give me the number" from "explain
   the methodology."

The fix was what the human had asked for from the beginning: LLM-powered answers. The
keyword matcher and rigid formatter were deleted entirely. Now `answer_question()` gathers
state, formats it as context, and passes the question to Claude (haiku). The prompt tells
the LLM that the user is on Max, that cost data is API-equivalent, and to keep answers
concise and conversational. If the LLM fails, it falls back to raw state with a disclaimer.

## The Meta-Lesson

The orchestrator's answer_question() gap illustrates a pattern that appears in every software
project: the first implementation solves the surface problem. The real need only surfaces
when someone tries to use it and asks "but why doesn't it actually...?"

And then the second implementation gets field-tested and reveals a second layer of gaps:
keyword matching can't handle conversational questions, data labels need context to be
honest, and meta-questions require a different response pattern than data questions. Each
layer of feedback makes the bot more useful --- but only if someone is listening to what
the first real user actually types.

The 5 Whys analysis, now embedded in the design agents, exists to catch this pattern at
design time rather than after shipping. Whether it works depends on whether the analyst
(human or AI) is willing to keep asking "why" past the comfortable first answer.

## D. Background Polling

The last gap: the orchestrator only checked Slack at pipeline checkpoints --- between tasks.
If a task took twenty minutes, a question sat unanswered the entire time.

The fix is a daemon thread that polls Slack every 30 seconds, independent of the task loop.
`start_background_polling()` launches a `threading.Thread` that calls `process_inbound()` on
its own schedule. The main pipeline never blocks on it; it just starts the thread after
initializing `SlackNotifier` and stops it before printing the final summary.

The thread catches all exceptions from `process_inbound()` so a transient Slack API error
doesn't kill the polling loop. The `threading.Event`-based wait (instead of `time.sleep`) means
`stop_background_polling()` can signal an immediate exit rather than waiting for the full
interval to elapse.

## Verification

- Python syntax: clean
- Test suite: 68 tests passing (9 for answer_question, 8 for intake, 5 for background polling,
  46 existing)
- The existing `test_process_inbound_dispatches_feature` test was not broken by the intake
  routing change because it mocks `poll_messages` and doesn't go through the intake path
- Background polling tests verify: no-op when disabled, daemon thread creation, idempotency,
  safe stop without start, and error resilience (thread survives exceptions)
