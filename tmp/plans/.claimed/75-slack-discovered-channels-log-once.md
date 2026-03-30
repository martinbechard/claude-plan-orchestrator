# Slack "Discovered channels" message should only appear once at startup

The "[SLACK] Discovered channels: ..." message is logged repeatedly during pipeline operation. It should only be logged once when the orchestrator starts up, not on every poll cycle or reconnection.

## LangSmith Trace: 10b35fca-ee60-428f-b82b-fd1c16504888


## 5 Whys Analysis

**Title:** Slack "Discovered channels" message logged repeatedly instead of once at startup

**Clarity:** 4/5
(The problem and goal are explicit [C1, C2], but lacks technical context about the root cause mechanism.)

**5 Whys:**

W1: Why is the "[SLACK] Discovered channels: ..." message being logged repeatedly?
    Because: The Slack discovery/notification code executes on every poll cycle or reconnection event rather than only during initial orchestrator startup [C1] [ASSUMPTION]

W2: Why does the code execute the discovery logging on every poll cycle?
    Because: There is no persistent state tracking that records "I've already logged discovered channels" across the application lifecycle [ASSUMPTION]

W3: Why wasn't a "log once" flag or marker implemented?
    Because: The original implementation either didn't anticipate reconnection scenarios or treated channel discovery as a per-cycle operation rather than a startup-only operation [C2] [ASSUMPTION]

W4: Why should this only happen at startup rather than on every cycle?
    Because: Discovered channels are static (or rarely change), so re-logging them every poll cycle creates unnecessary log noise without providing updated information [C1] [ASSUMPTION]

W5: Why is log noise a problem worth fixing?
    Because: Excessive logging degrades observability—duplicate startup messages obscure meaningful events and make logs harder to parse for debugging [C1, C2] [ASSUMPTION]

**Root Need:** Implement a startup-only logging mechanism for discovered Slack channels so the message appears exactly once when the orchestrator initializes, not on subsequent poll cycles or reconnections, to reduce log noise while preserving the discovery information for debugging [C1, C2]

**Summary:** The Slack discovery message needs to be gated to occur only once at orchestrator startup to reduce log noise from repeated identical messages across reconnection cycles.
