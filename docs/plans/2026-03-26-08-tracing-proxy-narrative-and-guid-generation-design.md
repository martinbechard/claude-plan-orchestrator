# Design: Tracing Proxy Narrative and GUID Generation

## Overview

Two-part feature:
1. Write a narrative document explaining the origin and purpose of the local TracingProxy.
2. Investigate which LangSmith SDK calls still reach the network (vs. being intercepted by the proxy), and decide whether to implement self-generated trace/run GUIDs.

---

## Part 1 — Narrative Document

**File to create:** `docs/narrative/tracing-proxy.md`

No code changes required. Content is fully specified in the work item:
- Why LangSmith was used initially (early dev tracing)
- Why we built the local proxy (free credits exhausted, needed custom metrics)
- What the proxy does (intercept SDK HTTP calls, persist to SQLite, serve custom UI)
- That LangSmith forwarding is still supported via `forward_to_langsmith: true`

---

## Part 2 — LangSmith Call Investigation

**Goal:** Determine which LangSmith SDK calls are intercepted by the proxy vs. leak to `api.smith.langchain.com`.

**Approach:**
- Add request logging to the proxy's catch-all / unmatched routes to surface any SDK calls that hit the proxy but are not handled
- Run a pipeline job with network inspection (e.g., `HTTPS_PROXY` or mitmproxy) to observe outbound calls
- Alternatively, review the proxy's route registrations against known LangSmith SDK endpoints (POST /runs, PATCH /runs/{id}, GET /sessions)

**Key questions to answer:**
- Are PATCH /runs (run updates: end_time, outputs, error) intercepted?
- Are GET /sessions or session creation calls intercepted?
- Does any call require a valid LangSmith API key to succeed?

**Relevant files:**
- `langgraph_pipeline/web/proxy.py` — TracingProxy and DB layer
- `langgraph_pipeline/web/routes/analysis.py` — current route handlers
- `langgraph_pipeline/web/server.py` — FastAPI app and route registration

---

## Part 3 — GUID Decision

After Part 2 investigation, decide whether to:
- **Keep the LangSmith SDK** (IDs generated for free, minimal change)
- **Replace with direct proxy calls** + self-generated UUIDs (removes SDK dependency)

If self-generated IDs are chosen, use `uuid7` PyPI package (UUIDv7, time-ordered, same format as current LangSmith IDs).

This decision is captured as a task so the investigator's findings drive the outcome.

---

## Design Decisions

- The narrative doc is purely documentation — no tests needed, no code changes.
- The investigation task should add minimal logging (not full tracing infrastructure) to surface unhandled routes.
- Self-generated GUID implementation is deferred pending investigation findings.
- No new files or modules for Part 1; narrative lives under existing `docs/narrative/`.
