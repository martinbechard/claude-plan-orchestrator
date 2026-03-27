# Design: Dashboard Drill-Down to Trace (06) - Validation Pass

## Source
Defect: tmp/plans/.claimed/06-dashboard-drill-down-to-trace.md

## Implementation Status
This feature was previously implemented. The backlog item is flagged "Review Required"
meaning the acceptance criteria must be validated against the current codebase and any
gaps fixed.

## Architecture Overview

Each work item stores its LangSmith trace UUID in the claimed item markdown
file as a LangSmith Trace header. The worker creates this marker on first
run and re-uses the same UUID across restarts.

The implementation threads that UUID through:
1. WorkerInfo (in-memory active workers) - run_id field
2. CompletionRecord and the completions SQLite table - run_id column
3. The SSE snapshot payload and list_completions() return value
4. Dashboard HTML/JS rendering (anchor tag per row linking to /proxy?trace_id=<run_id>)

## Key Files to Validate

### Backend
| File | Expected State |
|------|----------------|
| langgraph_pipeline/web/dashboard_state.py | WorkerInfo and CompletionRecord have run_id field; snapshot() includes it |
| langgraph_pipeline/web/proxy.py | completions table has run_id column; record_completion and list_completions handle it |
| langgraph_pipeline/supervisor.py | Reads trace_id from claimed file at dispatch and reap; passes run_id to dashboard state and completion record |

### Frontend
| File | Expected State |
|------|----------------|
| langgraph_pipeline/web/templates/dashboard.html | Worker cards and completion rows render trace links when run_id is present |

## Acceptance Criteria (from backlog item)
1. Each active worker row has a link that opens /proxy?trace_id=<run_id>
2. Each recent completion row has the same link
3. If trace does not exist yet (worker still running), the link goes to filtered list (may be empty)

## Design Decisions (unchanged from prior implementation)
- Trace ID read at dispatch time from claimed file (may be None for first run)
- Trace ID re-read at reap time (guaranteed to be written by then)
- DB migration via ALTER TABLE guard for nullable run_id column
- Graceful degradation: no link rendered when run_id is None/empty
- URL format: /proxy?trace_id=<uuid> (depends on defect-05 trace_id filter)
