# Tracing proxy: narrative documentation and self-generated trace IDs

## Implementation Status: Review Required

This item was previously implemented and marked complete. Validate the
acceptance criteria below. If any criterion fails, fix it. Do not
rewrite from scratch — check what exists first.


## Status: Open

## Priority: Low

## Summary

Two related items bundled for consideration together:

1. Write a narrative document explaining why the local tracing proxy was built.
2. Investigate and optionally implement self-generated trace/run GUIDs when
   LangSmith forwarding is disabled.

---

## Part 1 — Narrative Document

Add docs/narrative/tracing-proxy.md explaining the origin and purpose of the
local TracingProxy:

- We were using LangSmith for tracing during early development.
- Free credits ran out and getting more was friction.
- We wanted more control over how trace data was displayed — LangSmith's UI
  did not surface the metrics we cared about (cost per work item, item type
  breakdown, pipeline throughput).
- The proxy was built as a dev-time tool: intercept the same HTTP calls the
  LangSmith SDK makes, persist them locally in SQLite, and serve a custom UI
  that shows exactly what we want.
- Forwarding to LangSmith is still supported (forward_to_langsmith: true in
  config) for teams that want both.

---

## Part 2 — Trace ID Origin and Self-Generated GUIDs

### Where do trace/run IDs come from today?

When LangSmith is active the LangSmith SDK generates UUIDs (UUIDv7 based on
timestamps, e.g. 019d288e-61b7-7402-...) for each run and sends them in the
POST /runs payload. The proxy intercepts these calls and stores the SDK-
generated run_id verbatim in the local DB. So trace IDs currently come from
the LangSmith SDK regardless of whether forwarding is enabled.

### What other LangSmith calls are still being made?

The SDK likely makes additional calls beyond POST /runs (e.g. PATCH /runs for
updates, GET /sessions). These are not currently intercepted — only the initial
run creation hits our proxy endpoint. Needs investigation:

- Run update calls (end_time, outputs, error) — do these hit the proxy?
- Session management calls — do these leak to api.smith.langchain.com?
- Are there any calls that require a valid LangSmith API key to succeed?

If the SDK still phones home for any of these even when our proxy is active,
that is a latent dependency worth removing.

### Self-Generated GUIDs (to ponder)

If we ever remove the LangSmith SDK entirely (replacing it with direct calls
to our proxy), we would need to generate our own run UUIDs. Options:

- UUIDv4 (random) — simple, no ordering guarantee
- UUIDv7 (time-ordered) — same format as current LangSmith IDs, sortable
  by creation time without a separate created_at column
- ULID — similar to UUIDv7, lexicographically sortable

Recommendation to evaluate: use UUIDv7 via the uuid7 PyPI package to maintain
compatibility with the existing DB schema and keep IDs time-sortable. Only
worth implementing if we decide to drop the LangSmith SDK dependency.

## Next Steps

1. Write the narrative doc (standalone, no code changes).
2. Add logging/inspection to determine which LangSmith SDK calls are still
   reaching the network vs. being intercepted.
3. Decide: keep SDK (simple, IDs generated for free) or replace with direct
   proxy calls + self-generated UUIDs.

## LangSmith Trace: c3fa02ff-c708-459c-8205-9aa6f013e5fe


## 5 Whys Analysis

Title: Establishing architectural independence and understanding tracing system dependencies

Clarity: 4/5 (Well-structured with clear deliverables; "investigate" is somewhat open-ended on scope)

5 Whys:

1. **Why document the tracing proxy's origin?**
   - Answer: To preserve the architectural rationale (LangSmith cost, need for custom metrics visibility) so future decisions about the tracing system are informed, not arbitrary

2. **Why is preserving that rationale important?**
   - Answer: Because without it, the team can't distinguish between core architectural choices and accidental dependencies, risking decisions to keep LangSmith when it's no longer needed

3. **Why would accidental dependencies matter?**
   - Answer: They lock the system into the LangSmith SDK even when forwarding is disabled, meaning the team can't achieve true local autonomy without redesigning trace ID generation

4. **Why does local autonomy matter?**
   - Answer: The proxy was built to replace LangSmith's limitations (cost, poor metrics), but if trace ID generation still depends on LangSmith, the core goal (freedom from that dependency) is incomplete

5. **Why is freedom from external dependencies a priority?**
   - Answer: So the local development environment is self-contained, predictable, and doesn't leak data or create latency to external services when LangSmith forwarding is disabled

**Root Need:** Verify and document that the local tracing system is architecturally independent from LangSmith, with no hidden SDK dependencies that undermine the original reason the proxy was built.

**Summary:** The team needs proof that their local tracing proxy is truly self-sufficient and intentional, not accidentally bound to LangSmith through overlooked dependencies.
