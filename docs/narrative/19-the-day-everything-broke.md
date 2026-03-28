# Chapter 19: The Day Everything Broke

**Period:** 2026-03-26 to 2026-03-27
**Scope:** Pipeline observability, quality gates, and the hunt for why nothing actually works

## The Illusion of Completion

By March 26, the pipeline had processed dozens of items. The dashboard showed green completion badges. The numbers looked impressive. Then we started actually looking at what was done.

Item after item marked "success" had no real implementation. The cost analysis page showed dummy data. The tilde prefix we'd asked to remove three times was still there. Items were being archived as complete after 10-second runs with zero cost. The validator was saying "cannot verify at validation time" and passing everything anyway.

The pipeline was a completion factory, not a quality factory.

## The 830-Cycle Loop

The first catastrophic discovery: items were being processed 240 times each in 2-second cycles. The root cause was embarrassingly simple — the backlog items discussed rate limiting, and their text contained the phrase "You've hit your limit." The quota detection regex matched this in Claude's response (which included the item text), flagged it as quota exhaustion, and the pipeline retried immediately. 830 cycles before anyone noticed.

The fix was surgical: check stderr for quota messages, not stdout (which contains Claude's response). But it revealed a deeper problem — the pipeline had no circuit breaker for repeated failures.

## The Permission Wall

The next wall: Claude Code treats all paths under `.claude/` as sensitive and blocks writes even with `--dangerously-skip-permissions`. The planner was trying to write YAML plans to `.claude/plans/` and getting denied 6 times per attempt, burning $0.60 each time on an Opus call that accomplished nothing.

We first built a hack to "rescue" the YAML content from the permission denial JSON. Then we ripped that out and moved the plans directory from `.claude/plans/` to `tmp/plans/` — the proper fix.

## The Token Tracking Saga

We wanted to see how fast workers were processing tokens. Simple, right? It took seven attempts:

1. Token metadata in traces DB — broken because langsmith 0.7.22 changed how `add_metadata` batches payloads
2. Direct DB merge via `proxy.merge_metadata` — wrote to the wrong trace row
3. Supervisor polling from traces DB — overwrote API-posted values with zeros
4. Worker POST to `/api/worker-stats` — worked but supervisor polling overwrote it
5. Removed supervisor polling — values dropped to zero on page refresh because completions had no tokens
6. Computed tokens from `velocity * duration` in completions — finally worked for completed items
7. Live stats during execution via the API — finally showed real-time velocity

The lesson: when three systems fight over the same data, pick one source of truth and delete the others.

## The Validator Problem

The validator agent was the weakest link. It would:
- Say "cannot verify at validation time" for every UI criterion
- Pass items where the planner failed to create a YAML
- Accept fake test data (100/50/0.01) as real results
- Use Sonnet instead of Opus for design work

Each of these was a separate fix, and each revealed another layer of the problem. The planner wasn't generating acceptance criteria. The intake wasn't running 5 Whys on features. The design validator was checking stdout for quota keywords. The `_invoke_claude` function was asking Claude to "read the file at .claude/plans/..." which it couldn't access.

## The Observability Gap

The most frustrating pattern: something would go wrong, and we couldn't tell what happened. Worker output went to stdout which went to a pipe which went nowhere. The planner's JSON response (including permission denials) was discarded. The validator's verdict was written to a file that got overwritten by the next task.

We built three layers of observability:
1. Per-item worker output logs saved to `docs/reports/worker-output/<slug>/`
2. Validation result JSON files persisted alongside the logs
3. `POST /api/worker-stats` for real-time token/cost updates to the dashboard

## The Quota Catastrophe

At the end of the day, quota ran out. In 60 seconds, 28 items were archived as "success" with $0 cost and 10-second durations. The workers couldn't reach Claude, got empty responses, and the pipeline happily archived everything as complete.

The fix: centralized quota detection in `call_claude` that sets a global flag, reports via API to the supervisor, and halts all dispatch until a probe confirms quota recovery.

## What We Learned

1. **Success is not completion.** An item marked "success" means the pipeline didn't crash, not that the work was done. The validator must verify, and the verification must be visible.

2. **One source of truth.** Token counts, cost, and velocity should flow through one path, not three competing systems.

3. **Show the work.** If you can't see what the agent did (tool calls, file reads, decisions), you can't diagnose why it did it wrong. Save everything.

4. **Test data is poison.** Round numbers (100/50/0.01) in a production database are never real. The validator must detect and reject them.

5. **Short-term fixes become permanent.** Every "we'll fix it properly later" hack from this day is still in the codebase because we stopped doing that and started fixing things properly.

6. **If you found it, fix it.** An audit that identifies 10 issues but only creates items for 7 of them means 3 issues will never be fixed. The cost of creating an item is zero. The cost of ignoring a known problem is unbounded.
