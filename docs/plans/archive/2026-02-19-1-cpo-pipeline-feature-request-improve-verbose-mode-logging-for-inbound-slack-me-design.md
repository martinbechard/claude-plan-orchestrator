# Design: Verbose Logging for Agent Identity Message Filtering

## Overview

Add `verbose_log()` calls to each branch of the agent identity filtering block
in `_process_inbound_messages()` (plan-orchestrator.py, lines 4826-4843). This
gives operators diagnostic visibility into why inbound Slack messages are
accepted or rejected during multi-instance operation.

## Architecture

### Affected File

- `scripts/plan-orchestrator.py` - `_process_inbound_messages()` method on
  the `Orchestrator` class (lines 4826-4843)

### Existing Convention

The codebase uses `verbose_log(message, prefix)` (defined at line 748) which
prints timestamped messages when `--verbose` is enabled. Existing prefixes
include "FIND", "DEPS", "PARALLEL", "PERM", "STOP", and "WORKTREE".

### Design Decisions

1. **Prefix choice:** Use "FILTER" as the prefix for all identity filtering
   log lines. This is descriptive and consistent with the existing naming
   convention (short, uppercase noun/verb).

2. **Log content:** Each log line includes:
   - The channel name (from `msg.get("_channel_name", "")`)
   - The decision outcome (skipped/accepted and why)
   - Relevant parsed data (signature name, addressees, our agent names)
   - A truncated preview of the message text (first 60 chars)

3. **Four decision points to instrument:**
   - **Rule 1 - Skip own agent:** Message signed by one of our agents
   - **Rule 2 - Skip addressed to others:** Message addressed to other
     agents but not to us
   - **Rule 3 - Accept addressed to us:** Message explicitly addressed to
     one of our agents
   - **Rule 4 - Accept broadcast:** Message with no agent addressing
     (broadcast to all)

4. **No identity block (passthrough):** When `_agent_identity` is None,
   log that identity filtering is disabled (once per message batch would
   be noisy; skip this case).

5. **Performance:** `verbose_log()` already checks the `VERBOSE` flag at
   the top, so there is zero overhead when verbose mode is off. The only
   new cost is string formatting for log lines, which is negligible.

### Example Output

```
[14:32:01.123] [FILTER] Skip own-agent: sig="CPO-Pipeline" channel=#orchestrator-notifications text="Pipeline: completed foo..."
[14:32:01.124] [FILTER] Skip addressed-to-others: addressees={Acme-Pipeline} ours={CPO-Pipeline, CPO-Orchestrator} channel=#orchestrator-questions text="@Acme-Pipeline what is..."
[14:32:01.125] [FILTER] Accept addressed-to-us: addressees={CPO-Pipeline} channel=#orchestrator-defects text="@CPO-Pipeline new bug..."
[14:32:01.126] [FILTER] Accept broadcast: no-addressees channel=#orchestrator-features text="Please add feature..."
```

## Testing

Add unit tests to `tests/test_plan_orchestrator.py` that verify
`verbose_log()` is called with the correct prefix and content for each of
the four filtering decisions. Use `unittest.mock.patch` on `verbose_log`.
