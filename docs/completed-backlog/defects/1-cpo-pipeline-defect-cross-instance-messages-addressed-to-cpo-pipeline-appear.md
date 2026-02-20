# @CPO-Pipeline Defect: Cross-instance messages addressed to @CPO-Pipeline appear 

## Status: Open

## Priority: Medium

## Summary

@CPO-Pipeline Defect: Cross-instance messages addressed to @CPO-Pipeline appear to be silently ignored, while @CPO-QA works.

Steps to reproduce:
1. MIQ-Orchestrator sent "@CPO-Pipeline Hello!" to #orchestrator-questions at 9:01 PM
2. No response received
3. A message addressed to "@CPO-QA What is the current pipeline status?" at 9:51 PM got a response within 1 minute

Expected: Addressing any of a project's agent names should route the message correctly — or at minimum, the protocol should clearly document which agent name is the public entry point for cross-instance communication.

Additionally: Verbose mode provides zero visibility into inbound message filtering decisions. When a message is skipped or processed, there is no log output explaining why. This makes it impossible to debug cross-instance issues without reading the source code. — *MIQ-Orchestrator*

## Source

Created from Slack message by U0AFJJ9KZQW at 1771556225.963669.
