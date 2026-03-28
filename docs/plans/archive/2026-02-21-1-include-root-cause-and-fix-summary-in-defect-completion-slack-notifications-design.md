# Design: Include Root Cause and Fix Summary in Defect Completion Slack Notifications

## Problem

When the pipeline archives a completed defect, the Slack notification only shows
the item name and duration. The human operator has no inline insight into what was
wrong or what was changed, forcing context-switches to inspect backlog files for
every completed defect. This makes it impractical to triage which fixes warrant
manual code review directly from Slack.

## Solution

Before archiving, read the defect markdown file and extract a concise 2-3 sentence
summary covering what was wrong (root cause) and what was changed (fix). Append
this summary to both the notifications channel and the type-specific channel
Slack messages.

## Architecture

### New function: _extract_completion_summary(item_path) in auto-pipeline.py

A module-level helper that reads the defect markdown file at item_path and
extracts a concise summary from available structured sections:

1. Looks for ## Root Cause section (explicit root cause statement)
2. Falls back to the Root Need line from 5 Whys analysis
3. Falls back to the first sentence of ## Summary section
4. Looks for the last verification log entry to extract fix details
5. Returns a formatted string or empty string if nothing extractable

The function is called BEFORE archive_item() since archiving moves the file
to a new location, making item.path stale.

```
def _extract_completion_summary(item_path: str) -> str:
    """Extract a concise root cause and fix summary from a completed item file.

    Reads the markdown file and extracts up to 2-3 sentences covering
    what was wrong and what was changed. Returns empty string if the file
    cannot be read or has no extractable sections.
    """
```

Extraction priority for "what was wrong":
- ## Root Cause section first sentence (most explicit)
- **Root Need:** line from 5 Whys (second choice)
- ## Summary first sentence (fallback)

Extraction for "what was fixed":
- Last verification entry findings that mention "fix" or "commit"
- Falls back to verdict line (e.g. "Verdict: PASS")

Output is truncated to MAX_SUMMARY_LENGTH (300 chars) to keep Slack messages
readable.

### Modification to _archive_and_report() in auto-pipeline.py

Insert a call to _extract_completion_summary(item.path) BEFORE archive_item()
and append the summary to both existing send_status() calls:

```
# Before archive — file still at original path
summary = _extract_completion_summary(item.path)

archived = archive_item(item, dry_run)
...
# Append summary to notification messages
summary_block = f"\n{summary}" if summary else ""
slack.send_status(
    f"*Pipeline: completed* {item.display_name}\n"
    f"Duration: {minutes}m {seconds}s{summary_block}",
    level="success"
)
```

The same summary_block is appended to the type-specific channel cross-post.

## Key Files

| File | Change |
|---|---|
| scripts/auto-pipeline.py | Add _extract_completion_summary() function; modify _archive_and_report() to call it before archiving and append result to Slack messages |
| tests/test_auto_pipeline.py | Unit tests for _extract_completion_summary() with various markdown structures |

## Design Decisions

- **Extract before archive.** archive_item() moves the file via shutil.move(),
  making item.path stale. The summary must be extracted first.
- **Graceful degradation.** If the file cannot be read or has no extractable
  sections, the notification is sent without a summary (existing behavior).
  No errors are raised.
- **Defect-agnostic extraction.** The function works on any markdown file with
  the standard sections. While the feature request targets defects, the function
  can be applied to features if desired in the future.
- **Truncation.** The summary is capped at MAX_SUMMARY_LENGTH (300 chars) to
  prevent Slack message bloat. Sections are extracted as first sentences, not
  full sections.
- **No LLM summarization.** The summary is extracted via regex from structured
  markdown sections. This avoids API calls, latency, and cost. The structured
  sections already contain concise human-readable content.
- **Single file change.** All logic stays in auto-pipeline.py. No changes
  to plan-orchestrator.py or SlackNotifier since the existing send_status()
  API is sufficient.
