# Design: Announce Completed Items in Type-Specific Slack Channels

## Problem

When `_archive_and_report()` successfully archives a completed backlog item, it
only sends a notification to `orchestrator-notifications`. Operators subscribed
to `orchestrator-features` or `orchestrator-defects` receive no completion signal
in the channel where they originally filed the request.

## Solution

After a successful archive, cross-post a completion announcement to the
type-specific channel (`orchestrator-features` for features,
`orchestrator-defects` for defects). The existing `orchestrator-notifications`
message is unchanged — the cross-post is additive.

## Architecture

### New method: `SlackNotifier.get_type_channel_id(item_type)` — `plan-orchestrator.py`

A new public method maps `item_type` ('feature' or 'defect') to the
corresponding Slack channel ID using the existing `_discover_channels()`
cache/API infrastructure. Placed immediately after the existing
`_get_notifications_channel_id()` method.

```python
def get_type_channel_id(self, item_type: str) -> str:
    """Return the channel ID for the type-specific channel.

    Maps item_type ('feature' or 'defect') to the corresponding Slack
    channel (e.g. orchestrator-features or orchestrator-defects) using
    the existing _discover_channels() infrastructure.

    Returns empty string if the channel is not found or Slack is disabled.
    """
    suffix_map = {"feature": "features", "defect": "defects"}
    suffix = suffix_map.get(item_type, "")
    if not suffix:
        return ""
    channel_name = f"{self._channel_prefix}{suffix}"
    channels = self._discover_channels()
    return channels.get(channel_name, "")
```

### Cross-post in `_archive_and_report()` — `auto-pipeline.py`

After the existing success `send_status()` call (which targets `orchestrator-notifications`),
add a second `send_status()` call that targets the type-specific channel:

```python
# Cross-post to type-specific channel (orchestrator-features or orchestrator-defects)
type_channel_id = slack.get_type_channel_id(item.item_type)
if type_channel_id:
    slack.send_status(
        f"*Completed:* {item.display_name}\n"
        f"Duration: {minutes}m {seconds}s",
        level="success",
        channel_id=type_channel_id,
    )
```

## Key Files

| File | Change |
|---|---|
| `scripts/plan-orchestrator.py` | Add `get_type_channel_id()` to `SlackNotifier` |
| `scripts/auto-pipeline.py` | Cross-post in `_archive_and_report()` after successful archive |
| `tests/test_plan_orchestrator.py` | Unit tests for `get_type_channel_id()` |

## Design Decisions

- **Cross-post, not replace.** The notifications channel message is preserved.
  The type-specific channel gets an additional announcement.
- **Silent if channel not found.** `get_type_channel_id()` returns an empty
  string when the channel isn't discovered. `_archive_and_report()` guards
  with `if type_channel_id:`, so missing channels are a no-op.
- **Reuse `_discover_channels()`.** No new Slack API calls — the method
  leverages the existing cached channel discovery, keeping the same
  rate-limit profile.
- **Method on `SlackNotifier`.** Channel-naming logic belongs in
  `SlackNotifier`, not scattered into `auto-pipeline.py`. This mirrors the
  existing `_get_notifications_channel_id()` pattern.
- **Suffix map is local.** The `suffix_map` dict inside `get_type_channel_id()`
  is intentionally local rather than a module constant — it is used only in
  this one method and the mapping is trivial.
