# Design: Synchronize Documentation with Current Codebase

## Overview

The codebase has grown significantly since the documentation was last updated. The README.md claims ~3,500 total lines across two scripts; the actual count is ~6,722 lines. Eight major features are undocumented, and the narrative history stops at Chapter 12 while development has continued.

This plan audits all documentation against the current codebase and brings it up to date.

## Scope

### Files to Modify

1. **README.md** - Major update: add missing feature sections, fix line counts, update directory tree
2. **docs/narrative/README.md** - Update line counts, add timeline entries for recent features

### Files to Create

3. **docs/narrative/13-self-improvement.md** - New chapter covering features #1-6 (multi-project Slack channels, intake acknowledgment, hot-reload, cost formatting improvements)

### Out of Scope

- Creating separate standalone guides (Slack setup, agent dev guide, etc.) - these would be nice but are beyond the current documentation sync task
- Architecture diagrams - these would require a separate feature request
- Updating individual narrative chapters (1-12) retroactively - they capture history at a point in time

## Gap Analysis

### README.md Gaps

| Section | Gap | Priority |
|---------|-----|----------|
| Line counts | Shows ~2095 + ~1450 = ~3500; actual is ~4773 + ~1949 = ~6722 | High |
| Agents | Only mentions coder/code-reviewer in examples; missing 8 agents | High |
| Slack Integration | Not mentioned at all | High |
| Budget/Quota Management | Not mentioned at all | High |
| Model Escalation | Not mentioned at all | High |
| Per-Task Validation | Not mentioned at all | High |
| Design Agents | Not mentioned at all | Medium |
| Hot-Reload | Not mentioned at all | Medium |
| Agent Framework | Brief mention, no detail on agent definitions | Medium |
| Directory tree | Missing agents/, slack config, etc. | Medium |
| Requirements | Missing slack_sdk dependency | Low |
| Overview bullet points | Incomplete feature list | Medium |

### docs/narrative/README.md Gaps

| Section | Gap |
|---------|-----|
| Timeline | Missing Feb 17 entries (hot-reload, intake ack, cost fixes) |
| Line count | Shows ~2095 + ~1450; should be ~4773 + ~1949 |
| Chapter 13 | Missing - no narrative covering recent self-improvement features |
| Intro paragraph | Says "three-and-a-half thousand lines" - actually ~6,700 |

## Design Decisions

1. **README sections ordered by importance**: Slack, Budget, Validation, Agents, Escalation, Hot-Reload
2. **Narrative chapter covers themes not features**: Chapter 13 groups recent features under the theme of "self-improvement" - the system improving itself
3. **No breaking changes**: All updates are additive documentation, no code changes
4. **Keep narrative voice**: The narrative README has a distinctive first-person voice; Chapter 13 maintains that style
5. **Update only stale numbers**: Fix specific line counts and feature lists; do not rewrite existing accurate content

## Task Breakdown

1. **Phase 1 - README.md Update**: Audit and update all sections of the main README
2. **Phase 2 - Narrative Update**: Update docs/narrative/README.md timeline and line counts
3. **Phase 3 - New Narrative Chapter**: Write Chapter 13 covering recent features
4. **Phase 4 - Verification**: Review all updated docs for accuracy and consistency
