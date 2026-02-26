# Design: Verbose Logging for Agent Identity Message Filtering

## Overview

Add verbose_log() calls to the agent identity filtering block in
_handle_polled_messages() (plan-orchestrator.py, ~lines 5570-5587). This gives
operators diagnostic visibility into why inbound Slack messages are accepted or
rejected during multi-instance operation.

## Architecture

### Affected File

- scripts/plan-orchestrator.py - _handle_polled_messages() method on
  the SlackNotifier class (agent identity filtering block around lines 5570-5587)

### Existing Convention

The codebase uses verbose_log(message, prefix) (defined at line 829) which
prints timestamped messages when --verbose is enabled. Existing prefixes
include "FIND", "DEPS", "PARALLEL", "PERM", "STOP", and "WORKTREE".

The filtering block already has unconditional print() statements using the
[SLACK] Filter: format. The verbose_log() calls add a structured diagnostic
layer toggled by --verbose, complementing the always-on prints.

### Design Decisions

1. Prefix choice: Use "FILTER" as the prefix for all identity filtering
   verbose_log lines. Consistent with existing short uppercase naming.

2. Log content: Each verbose_log line includes:
   - The channel name (from ch_log variable)
   - The decision outcome (skipped/accepted and why)
   - Relevant parsed data (signature name, addressees, our agent names)
   - A truncated preview of the message text (first 60 chars via preview)

3. Four decision points to instrument:
   - Rule 1 - Skip own agent: Message signed by one of our agents (this is
     the self-origin block at ~line 5558-5568)
   - Rule 2 - Skip addressed to others: Message addressed to other agents
     but not to us (~line 5577-5581)
   - Rule 3 - Accept addressed to us: Message explicitly addressed to one
     of our agents (~line 5582-5584)
   - Rule 4 - Accept broadcast: Message with no agent addressing (~line 5585-5587)

4. Implementation approach: Add verbose_log() calls adjacent to the existing
   print() statements. The prints remain for always-on output; verbose_log()
   adds richer structured detail visible only with --verbose.

5. Performance: verbose_log() checks the VERBOSE flag at the top, so there
   is zero overhead when verbose mode is off. The only new cost is string
   formatting for log lines, which is negligible.

### Example Output

```
[14:32:01.123] [FILTER] Skip own-agent: sig="CPO-Pipeline" channel=#orchestrator-notifications text="Pipeline: completed foo..."
[14:32:01.124] [FILTER] Skip addressed-to-others: addressees={Acme-Pipeline} ours={CPO-Pipeline, CPO-Orchestrator} channel=#orchestrator-questions text="@Acme-Pipeline what is..."
[14:32:01.125] [FILTER] Accept addressed-to-us: addressees={CPO-Pipeline} channel=#orchestrator-defects text="@CPO-Pipeline new bug..."
[14:32:01.126] [FILTER] Accept broadcast: no-addressees channel=#orchestrator-features text="Please add feature..."
```

## Testing

Add unit tests to tests/test_plan_orchestrator.py (or tests/test_slack_notifier.py
if that is where the filtering tests live) that verify verbose_log() is called with
the correct prefix and content for each of the four filtering decisions. Use
unittest.mock.patch on verbose_log.
