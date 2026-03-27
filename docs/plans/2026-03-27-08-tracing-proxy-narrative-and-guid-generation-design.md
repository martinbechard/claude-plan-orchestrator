# Design: Tracing Proxy Narrative and GUID Generation

## Overview

Two-part feature:
1. Write a narrative document explaining the origin and purpose of the local TracingProxy.
2. Investigate which LangSmith SDK calls still reach the network vs. being intercepted by the proxy, and document findings including a GUID generation recommendation.

## Part 1 -- Narrative Document

**File to create:** docs/narrative/tracing-proxy.md

Documentation-only task. Content is specified in the work item:
- Why LangSmith was used initially (early dev tracing)
- Why the local proxy was built (free credits exhausted, custom metrics needed)
- What the proxy does (intercept SDK HTTP calls, persist to SQLite, serve custom UI)
- That LangSmith forwarding remains supported via forward_to_langsmith config

No code changes, no tests.

## Part 2 -- LangSmith Call Investigation and GUID Decision

**Goal:** Determine which LangSmith SDK calls the proxy intercepts vs. which leak to api.smith.langchain.com.

**Approach:**
- Review proxy route registrations against known LangSmith SDK endpoints
- Check if PATCH /runs (run updates), GET /sessions, session creation are handled
- Identify any calls requiring a valid LangSmith API key
- Add catch-all logging for unhandled SDK routes if missing

**Key files:**
- langgraph_pipeline/web/proxy.py -- TracingProxy and DB layer
- langgraph_pipeline/web/routes/proxy.py -- proxy route handlers
- langgraph_pipeline/web/routes/analysis.py -- analysis route handlers
- langgraph_pipeline/web/server.py -- FastAPI app and route registration
- langgraph_pipeline/shared/langsmith.py -- LangSmith integration

**GUID decision:** After investigation, document whether to keep the LangSmith SDK (IDs generated for free) or replace with direct proxy calls + UUIDv7 self-generated IDs. The recommendation goes in the narrative doc as a "future direction" section.

## Design Decisions

- Narrative doc lives under existing docs/narrative/ directory
- Investigation findings are appended to the narrative doc as a technical appendix
- No new Python packages unless the decision is to implement self-generated GUIDs now
- Minimal code changes: only add catch-all route logging if investigation reveals gaps
