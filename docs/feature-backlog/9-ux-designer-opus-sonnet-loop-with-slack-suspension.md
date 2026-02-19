# UX Designer Opus/Sonnet Loop with Slack-Based Question Suspension

## Status: Open

## Priority: Medium

## Summary

Two related enhancements to the UX design pipeline:

1. **Opus/Sonnet design loop (immediate):** The `ux-designer` agent runs as Opus and
   acts as a stateful orchestrator. It produces a detailed design brief, then invokes
   a Sonnet subagent (`ux-implementer`) to realize the design. Sonnet returns either
   a complete design document or a structured question. When Opus receives a question,
   it answers using its own reasoning, injects the Q&A into the next Sonnet invocation
   (since Sonnet has no memory between calls), and loops until a complete design is
   produced. Any assumptions Opus made while answering questions are documented in the
   design output.

2. **Slack-based question suspension (follow-on):** When Opus cannot resolve a design
   question on its own, instead of guessing it suspends the work item. The pipeline
   posts the question to the features/defects Slack channel (where the user already
   monitors for completion confirmations), then continues processing other items. When
   the user answers in Slack, the system correlates the reply back to the suspended
   item and reinstates it into the queue with the answer injected as context.

## Desired Outcome

### Part 1 - Opus/Sonnet Loop

- UX design tasks produce higher quality output because Opus handles open-ended
  requirements reasoning while Sonnet handles creative visual/interaction generation.
- Ambiguities are surfaced and resolved within the design task rather than silently
  baked into the design.
- The YAML plan is unchanged — this is internal to the `ux-designer` task.

### Part 2 - Slack Suspension

- The user sees a question in the same Slack channel they already watch, in a format
  that makes it obvious what work item it belongs to and what is being asked.
- The pipeline does not stall waiting for an answer — other features and defects
  continue processing.
- When the user replies, the suspended item resumes automatically with the answer
  available to the agent, without manual intervention.
- The user later receives the normal completion confirmation for the item in the same
  channel, closing the loop.

## Key Design Advice

### Part 1

- Sonnet's output must use a rigid structured format (e.g. `STATUS: QUESTION` /
  `STATUS: COMPLETE`) so Opus can parse it reliably without ambiguity.
- Opus must treat each Sonnet invocation as fully stateless — the full Q&A history
  must be re-injected every time.
- Cap the loop (e.g. 3 rounds) to prevent runaway costs; after the cap, Opus
  documents remaining open questions and produces a best-effort design.

### Part 2

- The correlation between question and answer is the key technical challenge. The
  question message should embed a unique ID (e.g. item slug + timestamp) that the
  user's reply must reference, or use Slack threads so replies are automatically
  scoped to the question.
- "Suspended" is a new work item state distinct from "failed" — the item stays on
  disk, is excluded from normal processing, and has a pending-question marker file
  the pipeline checks on each cycle.
- The reinstatement path must inject the answer as part of the task context, not
  just restart the item from scratch.

## Dependencies

- Part 1 is self-contained and can be implemented now.
- Part 2 depends on Part 1 and requires changes to the auto-pipeline work item state
  machine and the Slack inbound message handling.
