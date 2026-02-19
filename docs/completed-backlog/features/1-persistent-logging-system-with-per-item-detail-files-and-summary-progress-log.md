# Persistent Logging System with Per-Item Detail Files and Summary Progress Log

## Status: Open

## Priority: Medium

## Summary

Implement a two-tier logging system in `auto-pipeline.py` and `plan-orchestrator.py`: a `logs/` directory containing one detailed log file per backlog item (named to match the item) capturing all console output for that item's full lifecycle, plus a top-level `logs/pipeline.log` capturing summary events only (item started, completed, warnings, errors). All existing `print()` calls should route through a logging facade so no call-site changes are needed. Log files persist across restarts, appending new runs with timestamped session headers.

## 5 Whys Analysis

  1. **Why do we need console outputs saved to log files?** Because the pipeline runs autonomously and console output is ephemeral — once the terminal session ends or scrolls, diagnostic information is lost.
  2. **Why is ephemeral console output a problem for an autonomous pipeline?** Because there is no human watching the terminal in real time, so any failure or anomaly that occurs mid-run leaves no trace to examine after the fact.
  3. **Why does the absence of a post-run trace make failures hard to diagnose?** Because the orchestrator makes dozens of sequential decisions per item (planning, implementing, verifying) and the failure point could be anywhere in that chain — without logs, the entire chain is opaque.
  4. **Why is opacity across the decision chain a meaningful operational risk?** Because operators must re-run expensive, non-deterministic Claude API workloads just to observe behavior, and re-runs may not reproduce the same failure since Claude's responses vary.
  5. **Why does a two-tier structure (per-item detail + global summary) solve this better than a single log?** Because a flat log mixing all items becomes unnavigable at scale: diagnosing one item requires filtering thousands of lines, while the summary gives operators a fast health check without exposing them to noise.

**Root Need:** Autonomous pipeline runs need durable, structured audit trails organized by work item so operators can diagnose failures in the exact context they occurred, without re-running expensive and non-deterministic workloads.

## Source

Created from Slack message by U0AEWQYSLF9 at 1771419962.264799.
