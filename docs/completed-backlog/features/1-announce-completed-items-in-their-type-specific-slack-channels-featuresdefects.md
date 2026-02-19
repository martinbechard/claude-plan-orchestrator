# Announce completed items in their type-specific Slack channels (features/defects)

## Status: Open

## Priority: Medium

## Summary

When `_archive_and_report()` in `auto-pipeline.py` successfully archives a completed item, it should send an additional announcement to the type-specific Slack channel (`orchestrator-features` for features, `orchestrator-defects` for defects) alongside the existing `orchestrator-notifications` message. This requires the `SlackNotifier` to resolve the target channel by item type using the existing `_discover_channels()` / channel-prefix infrastructure in `plan-orchestrator.py`. The notification channel message remains unchanged; the new announcement is a cross-post, not a replacement.

## 5 Whys Analysis

  1. Why do we want to announce completions in -features and -defects channels?

**Root Need:** The autonomous pipeline lacks targeted completion feedback — operators and stakeholders need completion announcements delivered to the same topic channel where work was requested, enabling low-effort oversight without sifting through a general notifications firehose.

## Source

Created from Slack message by U0AEWQYSLF9 at 1771451664.886579.
