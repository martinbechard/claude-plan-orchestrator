# Items Completed 2026-03-26 — Pending Review

47 items need validation review. Process each by requeueing with
`validate_only: true` in the plan YAML meta section.

## Review Queue (oldest first)

| # | Slug | Type |
|---|------|------|
| 1 | 02-traces-runs-named-langgraph | defect |
| 2 | 03-dashboard-items-stuck-running | defect |
| 3 | 01-traces-model-filter-broken | defect |
| 4 | 07-timeline-bar-colors-too-similar | defect |
| 5 | 04-timeline-duplicate-labels-and-elapsed-time | defect |
| 6 | 09-completions-finished-invalid-date | defect |
| 7 | 08-timeline-sub-second-precision-lost | defect |
| 8 | 11-nav-active-item-styling | defect |
| 9 | 05-traces-trace-id-column-and-filter | defect |
| 10 | 10-error-stream-always-empty | defect |
| 11 | 06-dashboard-drill-down-to-trace | defect |
| 12 | 13-timeline-all-items-show-as-other | defect |
| 13 | 08-tracing-proxy-narrative-and-guid-generation | feature |
| 14 | 05-queue-page | feature |
| 15 | 06-work-item-detail-page | feature |
| 16 | 15-traces-timestamps-utc-not-local | defect |
| 17 | 14-intake-analysis-silent-failure | defect |
| 18 | 18-work-item-duplicate-traces | defect |
| 19 | 16-tool-calls-missing-from-traces | defect |
| 20 | 17-trace-expand-chevron-duplicate-and-inline | defect |
| 21 | 04-dashboard-scrolling-timeline-view | feature |
| 22 | 09-verification-notes-in-work-item-page | feature |
| 23 | 07-completions-paged-table | feature |
| 24 | 10-trace-cost-analysis-page | feature |
| 25 | 12-inclusive-cost-precomputation | feature |
| 26 | 11-tool-call-cost-attribution | feature |
| 27 | 22-cost-data-gaps-in-traces | defect |
| 28 | 13-trace-observability-gaps | feature |
| 29 | 19-validator-marks-incomplete-work-as-done | defect |
| 30 | 20-worker-trace-link-finds-nothing | defect |
| 31 | 14-dashboard-timeline-wall-clock-with-navigation | feature |
| 32 | 01-audit-design-docs-for-validity | analysis |
| 33 | 15-session-tracking-and-cost-history | feature |
| 34 | 28-cost-by-node-type-display-bugs | defect |
| 35 | 29-duplicate-trace-rows-start-and-end-events | defect |
| 36 | 27-tool-call-cost-attribution-dummy-data | defect |
| 37 | 25-migrate-tests-off-legacy-plan-orchestrator | defect |
| 38 | 16-worker-velocity-tracking | feature |
| 39 | 03-cost-analysis-db-backend | feature |
| 40 | 30-cost-posting-uses-wrong-env-var-and-is-never-wired | defect |
| 41 | 17-work-item-status-clarity | feature |
| 42 | 33-wire-up-real-cost-data-pipeline | feature |
| 43 | 35-work-item-page-missing-requirements-from-backlog-file | defect |
| 44 | 38-tool-call-attribution-table-missing-attribution-column | defect |
| 45 | 39-scan-backlog-trace-confusing-inputs-outputs | defect |
| 46 | 40-remove-redundant-scan-backlog-node | defect |
| 47 | 41-rename-misleading-graph-nodes | defect |
| 48 | 37-ui-quality-process-lost-in-langgraph-migration | defect |

## Skipped (known status)

- 21-intake-throttle (fixed manually)
- 31-validation-criteria (implemented directly)
- 32-test-data-cleanup (implemented directly)
- 34-remove-tilde-third-attempt (known failed — tildes remain)
- 42-task-status-json (pipeline + manual fix)
- 43-capture-raw-worker-output (just completed)
- 44-cost-analysis-tooltip (just completed)
- 12-cost-tilde-prefix-remove (superseded by 34)
- 26-remove-tilde-from-templates (superseded by 34)
- 36-cost-analysis-ui-polish (known bad — used collapsible not tooltip)
