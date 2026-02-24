# Include root cause and fix summary in defect completion Slack notifications

## Status: Open

## Priority: Medium

## Summary

When the pipeline archives a completed defect, extract the root cause and fix summary from the defect's status file or verification output and include it in the Slack notification. The summary should be concise (2-3 sentences max) covering what was wrong and what was changed, appended to the existing completion message in both the general and type-specific channels. This enables the human operator to triage which fixes need manual code review directly from Slack, supporting effective oversight of autonomous pipeline operations.

## 5 Whys Analysis

  1. Why do we want root cause and fix summary in the Slack notification? Because the current defect completion notification only shows the item name and duration, giving the human no insight into what was actually wrong or what the AI changed.
  2. Why does the human need to know what was wrong and what changed from Slack? Because the pipeline runs autonomously and Slack is the primary monitoring channel — without semantic content, the human must context-switch to inspect backlog files for every completed defect.
  3. Why is context-switching to inspect files a problem? Because it breaks the human's workflow and makes it impractical to maintain continuous oversight when multiple defects are being processed, leading to fixes going unreviewed.
  4. Why is it important that fixes get reviewed? Because the AI pipeline has significant autonomy over the codebase, and some fixes (e.g., pipeline logic, data handling) carry higher risk than others — the human needs to triage which ones warrant manual code review.
  5. Why does the human need to triage fix risk from the notification itself? Because effective oversight of autonomous AI operations requires enough inline context to make review decisions at the point of notification, rather than requiring a separate investigation step that may be skipped under time pressure.

**Root Need:** The human operator needs inline semantic context in Slack notifications to maintain effective, low-friction oversight of autonomous AI pipeline work — enabling immediate risk triage without leaving the monitoring channel.

## Source

Created from Slack message by U0AEWQYSLF9 at 1771651242.970589.
