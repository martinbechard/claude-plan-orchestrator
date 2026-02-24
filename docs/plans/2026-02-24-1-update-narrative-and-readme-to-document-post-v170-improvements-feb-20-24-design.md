# Design: Update Narrative and README for Post-v1.7.0 Improvements (Feb 20-24)

## Overview

Write Chapter 16 of the project narrative and update README/narrative README to reflect the six completed items from the Feb 20-24 period. This is a documentation-only change --- no code modifications.

## Completed Items to Synthesize (Feb 20-24)

### Defects (3)
1. **Sandbox mode missing --permission-mode flag** - The sandbox feature shipped with an incomplete CLI flag combination, causing Write/Edit operations to deadlock in headless sessions. Root cause: two independent permission axes (tool availability vs. approval behavior) were not both handled.
2. **Infinite loop when failed task blocks dependents (deadlock detection)** - The orchestrator and pipeline lacked plan-level deadlock detection. When a failed task blocked all remaining dependents, the system looped infinitely. Fix: added deadlock detection that recognizes unreachable pending tasks and sets plan status to failed.
3. **Cross-instance agent permission complaints** - The cheapoville pipeline agent was missing Write permissions because the sandbox upgrade path was incomplete for consumer projects.

### Features (3)
4. **Root cause and fix summary in defect completion notifications** - Extracts a concise root cause and fix summary from completed defect files and includes it in Slack notifications, enabling risk triage from the monitoring channel.
5. **Improve README docs on cross-project Slack reporting** - Added consumer-facing setup instructions for cross-instance defect/feature reporting, turning an emergent capability into a documented workflow.
6. **Single-command onboarding for existing Slack workspaces** - Documented the copy-pasteable setup-slack.py command for adding orchestrator to a second project reusing an existing Slack app.

## Narrative Theme

**"The system learning to detect and communicate its own failure modes."**

The connecting thread across all six items is maturity in failure handling:
- The sandbox defect revealed the system did not understand its own permission model (two-axis permissions)
- The deadlock defect showed the system could not detect when it was stuck (no plan-level state machine)
- The cross-instance permission issue showed downstream projects inheriting incomplete configurations
- The richer notifications teach the system to explain what went wrong, not just that something completed
- The documentation items codify tacit knowledge, making the system's operational model explicit

## Key Files to Modify

| File | Change |
|------|--------|
| docs/narrative/16-failure-awareness.md | **NEW** - Chapter 16 narrative (~200-300 lines) |
| docs/narrative/README.md | Add Chapter 16 to index, update timeline, update line counts and stats |
| README.md | Update line counts (~5809 + ~3277), completed plans count, Development History bullets |

## Current Stats (for reference)
- plan-orchestrator.py: ~5809 lines
- auto-pipeline.py: ~3277 lines
- Total: ~9086 lines
- Completed defects: 18
- Completed features: 36
- Total completed items: 54
- Last narrative chapter: 15 (The Loop That Wouldn't Stop, 2026-02-19)
- Last timeline entry: 2026-02-19, Agent identity protocol (1.7.0)
- Current version: 1.7.0

## Task Breakdown

### Task 1.1: Write Chapter 16 and update narrative README
- Create docs/narrative/16-failure-awareness.md in the first-person AI narrator voice
- Synthesize the six items into the theme of failure awareness
- Update docs/narrative/README.md: add Chapter 16 to Document Index, add Feb 20-24 timeline entries, update line counts and completed plans count

### Task 1.2: Update main README.md
- Update line count references (~5809 orchestrator + ~3277 auto-pipeline)
- Update completed plans/items count
- Add Development History bullets for the Feb 20-24 improvements
- Update the "Current:" line in narrative README stats section

## Design Decisions

1. **Chapter number 16** - Follows sequentially from Chapter 15 (The Loop That Wouldn't Stop)
2. **Title: "Failure Awareness"** - Captures the theme of the system learning about its own failure modes
3. **Two tasks, not six** - The items are thematically connected and should be written as one narrative, not individual sections. README updates are a separate task since they depend on the chapter existing.
4. **No code changes** - This is purely documentation; no version bump needed since no functional changes are made
