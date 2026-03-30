# Design: 75 Slack Discovered Channels Log Once

Source item: tmp/plans/.claimed/75-slack-discovered-channels-log-once.md
Requirements: docs/plans/2026-03-30-75-slack-discovered-channels-log-once-requirements.md

## Architecture Overview

The "[SLACK] Discovered channels: ..." message is emitted by the
_discover_channels() method in two files:

- langgraph_pipeline/slack/poller.py (SlackPoller._discover_channels)
- langgraph_pipeline/slack/notifier.py (SlackNotifier._discover_channels)

Both methods use a time-based cache (SLACK_CHANNEL_CACHE_SECONDS = 300s).
When the cache expires, the method re-fetches channels from the Slack API and
re-logs the discovery message. This produces repeated identical log lines
throughout the pipeline lifetime.

The fix introduces a boolean flag _channels_logged on each class. The flag
starts False and is set to True after the first log. Subsequent cache refreshes
skip the print statement. This preserves the single startup log for debugging
while eliminating all duplicate messages.

## Key Files to Modify

- langgraph_pipeline/slack/poller.py - Add _channels_logged flag, gate print
- langgraph_pipeline/slack/notifier.py - Add _channels_logged flag, gate print
- tests/langgraph/slack/test_poller.py - Add tests for log-once behavior
- tests/langgraph/slack/test_notifier.py - Add tests for log-once behavior

## Design Decisions

### D1: Boolean guard flag for log-once semantics
- Addresses: P1, FR1
- Satisfies: AC1, AC2, AC3, AC4
- Approach: Add a _channels_logged: bool = False instance variable to both
  SlackPoller and SlackNotifier. In _discover_channels(), wrap the existing
  print statement with "if not self._channels_logged". Set the flag to True
  after the print executes. The flag is never reset, ensuring the message
  appears exactly once per process lifetime regardless of cache expiry or
  reconnection events. The print content remains unchanged, preserving the
  full channel list in the single log entry.
- Files:
  - langgraph_pipeline/slack/poller.py (modify)
  - langgraph_pipeline/slack/notifier.py (modify)
  - tests/langgraph/slack/test_poller.py (modify)
  - tests/langgraph/slack/test_notifier.py (modify)

## Design -> AC Traceability Grid

| AC | Design Decision(s) | Approach |
|---|---|---|
| AC1 | D1 | Message prints on first _discover_channels() call (startup) |
| AC2 | D1 | _channels_logged flag prevents repeat logs on subsequent poll cycles |
| AC3 | D1 | _channels_logged flag persists across cache expiry / reconnection |
| AC4 | D1 | Print content unchanged; full channel list in the single log entry |
