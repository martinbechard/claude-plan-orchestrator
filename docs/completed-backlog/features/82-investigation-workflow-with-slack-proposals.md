# Investigation workflow with Slack-based defect/enhancement proposals

Create a new pipeline workflow type "investigation" that analyzes an area of the codebase or a reported symptom, produces a list of proposed defects and enhancements, and presents them to the user via Slack for approval before filing.

## Workflow

1. User submits an investigation request (e.g. "investigate why item 74 has two dashboard entries and incomplete tasks")
2. Pipeline runs the investigation: reads relevant code, logs, data, and traces to identify root causes
3. Investigation produces a structured list of proposed backlog items, each with:
   - Proposed type (defect or enhancement)
   - Title
   - Description with evidence from the investigation
   - Severity/priority suggestion
4. Pipeline sends a Slack message to the appropriate channel summarizing the proposals in a numbered list
5. User replies to the Slack message indicating which proposals to accept (e.g. "1, 3, 4" or "all except 2" or "all")
6. Pipeline parses the user's response, matches it to the most recent proposal set for that investigation, and files the accepted items as backlog entries

## Key design considerations

### Proposal state persistence

The proposals must be persisted (not just held in memory) so that when the Slack poller receives the user's response, it can look up the most recent proposal set for that conversation. Options:
- Store proposals in the workspace as a structured YAML/JSON file keyed by investigation slug
- Store in the traces DB with a proposals table
- Store as a file in a known location (e.g. tmp/proposals/{slug}.yaml)

### Slack message threading

The proposal message and the user's response should be in a thread so the poller can match a reply to its parent proposal message. The proposal message's thread_ts should be stored with the proposal set.

### Response parsing

The user's response needs flexible parsing:
- "all" or "yes" - accept everything
- "none" or "no" - reject everything
- "1, 3, 5" - accept by number
- "all except 2" - accept with exclusions
- Free-text replies like "do the first three but skip the last one" should be handled by an LLM call

### Filing accepted items

Accepted proposals are written as markdown files to the appropriate backlog directory (docs/defect-backlog/ or docs/feature-backlog/) using the same format as manually created items. The investigation workspace should record which proposals were accepted and which were rejected.

### Relationship to existing analysis workflow

The analysis workflow currently produces a single analysis document. The investigation workflow differs in that:
- It produces multiple discrete actionable items rather than one document
- It requires a human-in-the-loop approval step via Slack
- Accepted items feed back into the pipeline as new work items

The investigation could reuse the analysis intake (clause extraction, 5 whys) for the initial request, but the output stage is entirely different.




## 5 Whys Analysis

Title: Investigation workflow with Slack-based proposal approval and auto-filing
Clarity: 4/5

5 Whys:

W1: Why do we need an "investigation" workflow type?
    Because users need to systematically analyze a symptom or area of the codebase and identify root causes, rather than discovering related issues ad-hoc. [C1, C2] [ASSUMPTION: root problem is discovery fragmentation]

W2: Why can't we just run the analysis and let the user file items manually?
    Because human-in-the-loop approval must happen in-context (via Slack thread) before filing, and accepted items need to automatically feed back into the pipeline rather than requiring manual backlog entry creation. [C24, C25, C5]

W3: Why does the approval specifically need to happen in a Slack thread?
    Because the proposals must be persisted and matched to user responses, and threading provides both persistence (message history) and traceability (parent/child relationship). [C12, C13, C8, C6]

W4: Why must we support flexible response parsing like "all except 2" and free-text?
    Because users will not consistently format their replies in a rigid format—some will say "1,3,5", others "all except 2", others natural language—and accepting any reasonable format reduces friction and user error. [C14, C15, C16, C17, C18, C19]

W5: Why do accepted proposals need to become backlog files rather than staying in memory?
    Because the pipeline processes items asynchronously across multiple runs, and persisting proposals as backlog entries ensures they're durable, trackable, and automatically picked up by the next pipeline cycle. [C20, C21, C25] [ASSUMPTION: backlog files are the single source of truth for pipeline work]

Root Need: Enable lightweight, Slack-driven investigation → proposal → approval → filing without context-switching, so investigation results automatically become backlog work items with minimal manual overhead and full traceability. [C1, C3, C4, C7, C20, C24, C25]

Summary: Automate the investigation-to-backlog pipeline with Slack threading and flexible approval, so systematic analysis outputs feed directly into work tracking without manual filing.
