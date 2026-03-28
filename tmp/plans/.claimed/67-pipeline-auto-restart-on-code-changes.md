# Pipeline should auto-restart when workers commit code changes that affect the web server

## Summary

When a worker commits changes to web routes, templates, or static files,
the running web server serves stale code. The validator then fails because
new routes return 404. The user has to manually restart the pipeline.

The hot-reload system (CodeChangeMonitor) already detects file changes and
can trigger a restart. But it only restarts the worker dispatch loop, not
the web server. The web server runs in a uvicorn thread that doesn't get
reloaded.

## Expected Behavior

When a worker commits changes to files under langgraph_pipeline/web/:
1. The hot-reload monitor detects the change
2. The web server is stopped and restarted with the new code
3. Active workers continue running (they don't depend on the web server)
4. The validator retries if it got a 404 due to stale server

## Acceptance Criteria

- After a worker adds a new route and commits, does the web server serve
  it without manual restart? YES = pass, NO = fail
- Do active workers continue running during the web server restart?
  YES = pass, NO = fail
- Does the validator retry once if it gets a 404 on a curl check?
  YES = pass, NO = fail

## LangSmith Trace: 7d99f028-ed57-4e90-af7b-03b8cca8b3b6


## 5 Whys Analysis

**Title:** Web server doesn't restart when code changes are deployed, causing validator failures until manual restart

**Clarity:** 4/5

The request clearly describes the problem and expected behavior. It could be slightly clearer about the impact timeline (e.g., how long validators are broken, whether active workers' validation gets blocked, or if this forces an entire pipeline restart).

---

**5 Whys:**

1. **Why does the validator fail when workers commit code changes?**
   Because the running web server continues serving stale code. New routes exist in the codebase but the uvicorn thread hasn't reloaded, so requests to new endpoints return 404.

2. **Why is the web server still serving stale code after changes are committed?**
   Because CodeChangeMonitor only restarts the worker dispatch loop. The uvicorn thread running the web server is not part of that restart signal, so it keeps the old process in memory.

3. **Why doesn't the file-change monitor include the web server in its restart logic?**
   Because the web server is architecturally decoupled—it runs as a long-lived background thread separate from the dispatch loop's monitored lifecycle. The monitor was designed only for reloading worker code, not server infrastructure.

4. **Why was the web server placed outside the monitored restart system?**
   Because the system separates concerns: the dispatch loop manages task execution (frequently changing), while the web server provides stable infrastructure (routes, validation endpoints, status pages). They were assumed to have different change frequencies and restart needs.

5. **Why must a human manually restart the pipeline to recover?**
   Because there's no automated recovery mechanism—no file-change detector for web/ files, no graceful shutdown signal for uvicorn, and no retry logic for transient 404s during a restart window.

---

**Root Need:** The pipeline needs a unified lifecycle manager that treats the web server and worker loop as a coordinated system, detecting web-layer changes and orchestrating server restarts without losing worker state, while handling transient failures during the transition.

**Summary:** The underlying issue is architectural separation of the web server from the monitored dispatch loop, requiring a unified restart orchestration system to automate what's currently manual.
