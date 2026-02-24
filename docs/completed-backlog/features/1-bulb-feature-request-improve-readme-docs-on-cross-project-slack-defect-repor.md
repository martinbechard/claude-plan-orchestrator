# :bulb: *Feature request: Improve README docs on cross-project Slack defect repor

## Status: Open

## Priority: Medium

## Summary

**Title:** Document cross-project Slack defect/feature reporting setup for consumer projects

**Classification:** feature - The README's cross-instance section describes the concept but never included consumer-facing setup instructions; this is missing documentation for a real capability, not a regression.

**5 Whys:**

1. **Why can't a consumer project easily report defects back to CPO via Slack?**
   Because the README's "Cross-Instance Collaboration" section explains what's possible architecturally but doesn't provide actionable setup steps — it reads as an overview, not a how-to guide.

2. **Why doesn't the README include actionable setup steps for consumer projects?**
   Because the documentation was written from the CPO maintainer's perspective (the upstream instance), not from the perspective of a downstream consumer project that wants to participate in cross-instance reporting.

3. **Why was the documentation written only from the upstream perspective?**
   Because `send_defect()` and `send_idea()` post to the project's own prefixed channels by default, and the mechanism for targeting another project's channels relies on implicit Slack workspace topology (shared channels + bot membership) rather than any explicitly documented orchestrator-level configuration.

4. **Why does cross-instance reporting rely on implicit Slack workspace topology instead of explicit configuration?**
   Because the design assumed adopters would already understand Slack channel mechanics, bot scoping, and channel-name resolution — no first-class "report upstream" API or configuration surface was created to make the routing explicit and discoverable.

5. **Why was no onboarding path designed for new adopters who want to report issues upstream?**
   Because the cross-instance feature was built as an emergent capability of the Slack integration rather than a planned user-facing workflow, so the knowledge required to set it up remained tacit in the maintainer's head instead of being codified in documentation.

**Root Need:** A consumer-facing onboarding guide that codifies the tacit knowledge required to set up cross-instance defect/feature reporting, turning an emergent capability into a documented, reproducible workflow.

**Description:**
Add a step-by-step "Reporting Issues to an Upstream Orchestrator" section to the README that walks a consumer project through: (1) which shared Slack channels must exist and their naming convention, (2) inviting the consumer bot to the upstream channels, and (3) how `send_defect`/`send_idea` route messages so they reach the right destination. This codifies the implicit setup knowledge and closes the gap between the architectural description of cross-instance collaboration and the practical steps a new adopter needs.

## Source

Created from Slack message by U0AG70DCQ1K at 1771688542.730169.
