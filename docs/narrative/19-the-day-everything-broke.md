# Chapter 19: The Day Everything Broke

**Period:** 2026-03-26 to 2026-03-28
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

## Day Two: The Quality Reckoning

### The Quota Catastrophe (Again)

We queued 48 items for review and went to sleep. Quota ran out. In 60 seconds, 28 items were archived as "success" with $0 cost and 10-second durations. The workers couldn't reach Claude, got empty responses, and the pipeline happily archived everything as complete. Again.

The fix this time was centralized: `call_claude` itself detects quota keywords in the response, sets a global `_quota_exhausted` flag, and POSTs to `/api/quota-exhausted` to tell the supervisor. The supervisor stops dispatching new workers and enters a 5-minute probe loop until quota recovers. Workers check `is_quota_exhausted()` and report failure instead of success.

### The Validator That Couldn't See

Every UI acceptance criterion got the same verdict: "cannot verify at validation time — requires runtime confirmation." The validator was giving up on every check that required looking at a web page. But the web server was running right there at localhost:7070.

First fix: tell the validator to use `curl` to check page content. Then the proper fix: update the validator prompt to write Playwright e2e tests for UI criteria, run them against the live server, and include the test results in the findings.

We also discovered that WARN verdicts were being recorded as SUCCESS in completions — the worker never checked the validation verdict before writing its result. Fixed by propagating `last_validation_verdict` from the executor subgraph through the pipeline state to the worker.

### The Baseline Problem

Every single validation was getting WARN because the build command referenced `scripts/plan-orchestrator.py` which had been deleted weeks ago. The validator dutifully reported this as a failure, even though it had nothing to do with the current item. Five of six WARN items had all acceptance criteria met — the WARN was solely from this stale config.

The short-term fix was to remove the stale reference. The long-term fix: the validator now runs a baseline check before evaluating changes. It stashes the current changes, runs build + tests to establish what was already broken, then restores and runs again. Only NEW failures count as regressions. Pre-existing failures are WARN, not FAIL.

### The Traces Page That Nobody Could Use

Two days of intense pipeline work, and the one page that should show what happened — the Traces page — was completely useless. Looking at it in a browser revealed the full horror:

- The first four rows all said "LangGraph" with identical trace ID prefixes. The user literally could not tell which work item any trace belonged to.
- The "Item slug" column repeated "LangGraph" — redundant with the run name, both useless.
- Duration showed 0.01 seconds for runs that took minutes (duplicate start/end trace events).
- Cost showed "—" for everything. Model showed "—" for most entries.
- Expanding a row showed "Metadata JSON" — a raw developer dump.
- The narrative view showed 8 phases all with 0.00s duration, duplicate entries for Planning and Execution, and "Unknown" labels for verification steps.

The requirements were rewritten from scratch: 17 specific problems documented from the live page, 6 user-centric use cases, and 13 binary acceptance criteria. A design competition with auto-judging was specified.

### Design Competitions Done Right

The old design competition process (Phase 0 from the early chapters) had been lost in the LangGraph migration. We rebuilt it properly:

1. The planner produces 3 design approaches, each explaining how every use case from the requirements is solved step by step.
2. A ux-reviewer agent (Opus) auto-judges all 3 approaches, scoring them against use cases and acceptance criteria, and selects a winner with written rationale.
3. The design validator (Opus) runs AFTER the judge picks, verifying the winning design has solid acceptance criteria and every use case addressed.
4. If the validator fails, the design is revised before implementation begins.
5. The frontend-coder must trace each use case through the implementation and verify it works end-to-end.

### Never Ship the Workaround

The most important lesson emerged from a simple exchange about the build command. After fixing the immediate problem (removing the stale reference), we were about to move on. But the right fix was a baseline check — and "we'll come back to it later" is a lie. We never come back.

This became a rule: never implement a short-term fix. Always do the proper fix. If the proper fix is too large, log it as high priority — but don't ship the workaround. Every hack from this session that we let slide would have become permanent technical debt.

Similarly: if an audit finds 10 problems, create items for all 10. The cost of creating an item is zero. Saying "not worth it" for 3 of them means those 3 never get fixed. If it was worth finding, it's worth fixing.
