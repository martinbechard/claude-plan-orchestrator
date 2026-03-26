# Remove ~ prefix from all cost displays

## Status: Open

## Priority: Low

## Summary

Every cost value is prefixed with ~ (e.g. "~$0.0123") to indicate it is an
estimate. This looks like a typo or broken character and adds no useful
information since users already understand API costs are estimates.

## Locations

- dashboard.js: session cost stat
- proxy.py _enrich_run(): display_cost field (~$x.xxxx)
- proxy_list.html: cost column
- analysis.html: any cost totals
- auto-pipeline.py / plan-orchestrator.py: any Slack or log messages that
  include cost

## Fix

Remove the ~ prefix everywhere cost is rendered. Display plain "$0.0123"
or "$1.23" without the tilde. If an approximation disclaimer is needed,
add a footnote or tooltip rather than a per-value prefix character.

## LangSmith Trace: f37e9ed5-8e60-44f7-89cc-766f27645be3
