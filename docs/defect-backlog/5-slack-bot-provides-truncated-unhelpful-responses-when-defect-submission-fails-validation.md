# Slack bot provides truncated, unhelpful responses when defect submission fails validation

## Status: Open

## Priority: Medium

## Summary

When defects are submitted via Slack, the bot must provide complete, untruncated responses that: (1) analyze whether the submission is truly a defect, (2) explain the classification decision, and (3) provide a clear reference to the created backlog item with its ID and title. The response should handle Slack's message length limits appropriately by summarizing or splitting messages if needed, ensuring users always receive actionable confirmation of their submission.

## 5 Whys Analysis

  1. **Why is the user frustrated?** Because the Slack bot's response was truncated ("when I terminante the auto-pipeline, I get some random hallucinated cost -this m") and didn't provide useful feedback about the defect submission.

**Root Need:** Users need reliable, complete confirmation when submitting defects through Slack that validates the submission, classifies it appropriately, and provides a clear reference to what was created.

## Source

Created from Slack message by U0AEWQYSLF9 at 1771305584.251029.
