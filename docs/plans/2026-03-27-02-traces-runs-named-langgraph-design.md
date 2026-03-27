# Design: Traces Runs Named "LangGraph" Fix Validation

## Problem

All root traces in the proxy traces list show the generic name "LangGraph" instead
of the actual work item slug. This makes the traces page unreadable since every run
looks identical.

## Current State

The fix was previously implemented across multiple files:

1. **langsmith.py** - create_root_run(item_slug, item_path) already creates RunTree
   with name=item_slug (not hardcoded "LangGraph")
2. **langsmith.py** - finalize_root_run() uses item_slug as the run name
3. **proxy.py** - record_run() persists the name from the RunTree to SQLite
4. **server.py** - HTTP interceptors (runs_multipart, runs_create) extract name
   from the LangSmith SDK payload and pass it to record_run()
5. **proxy_list.html** - Displays run.name in the "Run name" column and
   run.display_slug (from metadata) in the "Item slug" column

## Architecture

The trace name flows through this path:

    scan_backlog node
      -> slug = Path(filepath).stem
      -> create_root_run(slug, filepath)
         -> RunTree(name=item_slug, ...)
            -> post() to local proxy
               -> server.py runs_multipart/runs_create
                  -> proxy.record_run(name=run_data["name"])
                     -> SQLite traces table (name column)

## Key Files

- langgraph_pipeline/shared/langsmith.py - Root trace creation and finalization
- langgraph_pipeline/web/proxy.py - SQLite persistence, record_run ON CONFLICT clause
- langgraph_pipeline/web/server.py - HTTP interceptors for LangSmith SDK calls
- langgraph_pipeline/web/routes/proxy.py - _enrich_run display_slug from metadata
- langgraph_pipeline/web/templates/proxy_list.html - Trace list UI template
- langgraph_pipeline/pipeline/nodes/scan.py - Where slug is extracted and root trace created
- langgraph_pipeline/pipeline/state.py - PipelineState with item_slug field
- langgraph_pipeline/worker.py - Worker subprocess passes slug as run_name

## Scope

This is a "Review Required" defect - the fix was previously implemented. The task is
to validate the existing implementation against all acceptance criteria (DB query, UI
display, slug filtering) and fix any remaining gaps. No major architectural changes
are expected.

## Risks

- The ON CONFLICT clause in record_run does NOT update name - if the initial insert
  had the wrong name, subsequent updates won't fix it. This is by design (name should
  be correct on first insert).
- Old traces in the DB from before the fix will still show "LangGraph" - only new
  traces will have correct slugs.


## Acceptance Criteria

- Do root traces in the DB have names that match the actual work item slug
  (not "LangGraph")? Run: SELECT DISTINCT name FROM traces WHERE
  parent_run_id IS NULL ORDER BY created_at DESC LIMIT 10;
  YES (slugs visible) = pass, NO (all say "LangGraph") = fail
- Does the /proxy traces list page show the item slug in the Name column
  instead of "LangGraph"? YES = pass, NO = fail
- Can I filter traces by slug name and get meaningful results?
  YES = pass, NO = fail
