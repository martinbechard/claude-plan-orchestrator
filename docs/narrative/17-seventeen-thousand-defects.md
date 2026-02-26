# Chapter 17: Seventeen Thousand Defects

**Period:** 2026-02-25
**Size:** ~300 lines in `plan-orchestrator.py` (loop prevention layers A1-A5, BacklogRAG class B1-B3), 132 bogus files deleted, 12 new tests

## The Incident

The human woke up to 17,000 defect files in the backlog. Not real defects. The same defect, echoing through the system seventeen thousand times.

The mechanism was simple. The bot creates defect #17552. It sends a notification: ":white_check_mark: Defect received #17552 - some-defect.md". The notification lands in a channel the bot polls. The bot polls it back. The text is new (unique Slack timestamp), so dedup misses it. The LLM router sees what looks like a defect report and classifies it as a new intake. The intake system creates defect #17553 --- a defect about defect #17552. Then #17554 about #17553. Then #17555 about #17554.

Each notification was technically unique: different timestamp, different item number reference. The `_processed_message_ts` dedup couldn't help because each notification had a ts it had never seen before. The self-reply rate limiter (3 per 60 seconds) merely throttled the cascade to ~3 defects per minute instead of stopping it. At that rate, an overnight run produces thousands.

## Why Existing Defenses Failed

The pipeline already had defenses against self-loop processing, but they targeted the wrong problem.

**Timestamp dedup** tracks which message timestamps have been processed. But each notification is a genuinely different message with a different ts. The defect about #17552 is not the same message as the defect about #17553; it just happens to be caused by it.

**Self-reply windowing** (3 per 60s per channel) was the rate limiter that kept the flood to ~3/minute instead of ~4/second. It was designed for occasional self-echoes, not sustained cascading. The window resets, and three more get through. Every minute. For hours.

**Agent identity signing** prevents the bot from processing messages it signed with its own name. But the signature check happens at the message level, not the content level. Each notification has a unique body even though the *pattern* is identical.

The circuit breaker in the pipeline covers task execution failures, not Slack intake daemon threads. The intake threads run as fire-and-forget daemons; nothing counts how many have fired in the last hour.

## Four Layers Deep

The fix uses four independent mechanisms, any one of which would have prevented the incident. The redundancy is deliberate.

**Layer 1: Chain detection.** After creating defect #17552, the bot records `{item_number: 17552, slug: "some-defect", timestamp: now}` in a JSON file on disk. When a polled message contains "#17552" or the slug "some-defect", the bot recognizes it as referencing something it just created and skips it. The history file persists across restarts --- important because the loop can span restart cycles. Only the last 100 entries are kept, pruned after one hour. This is pure string matching against disk-persisted data; no LLM call needed.

**Layer 2: Tighter self-reply window.** The old parameters (3 per 60s) let too many through. The new parameters (1 per 300s) mean that after accepting one self-origin message on a channel, all others are blocked for five minutes. One message every five minutes cannot sustain a cascade.

**Layer 3: Bot notification pattern filter.** A regex matches the bot's own notification formats: emoji status indicators followed by "Defect received", "Feature created", "Received your defect request", etc. This catches the *pattern* regardless of which specific item number appears. The check runs before the LLM router, so matching messages never reach classification.

**Layer 4: Global intake rate limiter.** A hard cap of 10 intakes per 5-minute window, checked at the top of the intake analysis function. Even if every other layer fails simultaneously, the damage is capped at 10 items before the system refuses to create more. A loud warning is logged when this triggers.

A fifth, softer layer: the `MESSAGE_ROUTING_PROMPT` now tells the LLM that messages matching notification patterns should be classified as "none". This is the weakest defense (probabilistic) but reduces the chance of misclassification for edge cases.

## The Cleanup

132 bogus defect files (numbered 17561 through 17687) were deleted from `docs/defect-backlog/`. Their filenames told the whole story: `17561-whitecheckmark-defect-received-17552---17552-whitecheckmark-defect-recei.md`. The slug was generated from the notification text. Each file was a receipt for the loop's passage.

## RAG-Based Deduplication

The incident highlighted a broader problem: the intake system had no concept of "this request looks like something we already have." Even without the feedback loop, a human could submit the same defect twice with slightly different wording, and the system would happily create two separate backlog items.

The fix uses ChromaDB, an embedded vector database. On startup, the system indexes all existing backlog items into vector collections (one for defects, one for features). When a new intake comes in, after the 5 Whys analysis produces a title and description, the system queries the vector index for similar items. If any match exceeds a similarity threshold (0.75 cosine), it sends the candidates plus the new request to an LLM with a focused question: "Is this a duplicate? If so, which item?"

If confirmed as a duplicate, the new information is appended to the existing backlog file under an "Additional Report" section, and the user gets a Slack message saying "Consolidated with existing item #X". If not a duplicate, the item is created normally and added to the index.

ChromaDB runs embedded --- no server, no external service. It stores its data in `.claude/chroma/` and uses a lightweight sentence transformer model for embeddings. The dependency is optional; if chromadb is not installed, the dedup layer is silently skipped and the system creates items as before.

## The Defect That Predicted Itself

Defect #01 in the backlog --- the very first defect ever filed --- was titled "Self-skip filter drops legitimate messages." It complained that the bot_id filtering approach was too aggressive, dropping cross-instance messages that should have been processed. It recommended replacing the blanket sender-identity filter with targeted loop detection.

That recommendation sat in the backlog for six days while the pipeline processed other work. Then the feedback loop produced 17,000 files that proved the defect's thesis: the existing approach (skip by sender identity) was solving the wrong problem. The fix implements exactly what defect #01 recommended: detect the loop condition itself, not the message origin. The defect has been marked resolved.

## Verification

- Chain detection: message referencing recently created item #42 is skipped
- Self-reply window: second self-origin message within 300s is blocked
- Content filter: notification-format message caught by regex
- Rate limiter: 11th intake within 5 minutes is refused
- RAG dedup: similar existing item detected, consolidated instead of duplicated
- 614/614 tests pass
- plugin.json bumped to 1.8.0
