# Structured Requirements: 82 Investigation Workflow With Slack Proposals

Source: tmp/plans/.claimed/82-investigation-workflow-with-slack-proposals.md
Generated: 2026-03-31T21:10:24.065410+00:00

## Requirements

### UC1: Submit an investigation request
Type: functional
Priority: high
Source clauses: [C2, C31, C42]
Description: A user submits an investigation request describing a symptom, area of the codebase, or reported issue to be systematically analyzed. The request is expressed in natural language (e.g., "investigate why item 74 has two dashboard entries and incomplete tasks"). The investigation aims to replace ad-hoc discovery of related issues with a structured, systematic approach.
Acceptance Criteria:
- Can a user submit a natural-language investigation request to the pipeline? YES = pass, NO = fail
- Does the pipeline accept and begin processing the investigation request? YES = pass, NO = fail

### UC2: Review and approve proposals via Slack
Type: functional
Priority: high
Source clauses: [C10, C28, C32, C36, C37]
Description: After the pipeline posts a numbered list of proposals to Slack, the user replies in the same thread indicating which proposals to accept. The user may respond in any reasonable format: numbered lists ("1, 3, 4"), blanket acceptance ("all", "yes"), blanket rejection ("none", "no"), exclusion patterns ("all except 2"), or free-text natural language ("do the first three but skip the last one"). The system must handle all these formats without requiring the user to learn a rigid syntax, reducing friction and user error. The approval happens in-context via the Slack thread before any items are filed.
Acceptance Criteria:
- Can the user reply to the proposal Slack thread with their approval decisions? YES = pass, NO = fail
- Is the user able to use any of the documented response formats (numbered, all, none, exclusions, free-text)? YES = pass, NO = fail
- Does the approval happen in the Slack thread before filing occurs? YES = pass, NO = fail

### FR1: Investigation workflow type
Type: functional
Priority: high
Source clauses: [C1, C27, C30]
Description: The system must support a new pipeline workflow type called "investigation". Unlike the existing analysis workflow which produces a single analysis document, the investigation workflow produces multiple discrete actionable items and includes a human-in-the-loop approval step. The investigation may reuse the analysis intake stages (clause extraction, 5 whys) for the initial request, but the output stage is entirely different — it generates proposals rather than a document.
Acceptance Criteria:
- Does a new "investigation" workflow type exist in the pipeline? YES = pass, NO = fail
- Is the investigation workflow distinct from the existing analysis workflow? YES = pass, NO = fail
- Does the investigation produce multiple discrete items rather than a single document? YES = pass, NO = fail
- Can the investigation reuse analysis intake stages (clause extraction, 5 whys) for the initial request? YES = pass, NO = fail

### FR2: Investigation execution engine
Type: functional
Priority: high
Source clauses: [C3, C31]
Description: When an investigation is triggered, the pipeline reads relevant code, logs, data, and traces to identify root causes related to the submitted symptom or area. The investigation must systematically analyze the target rather than producing ad-hoc findings.
Acceptance Criteria:
- Does the pipeline read relevant code, logs, data, and traces during investigation? YES = pass, NO = fail
- Does the investigation identify root causes related to the submitted request? YES = pass, NO = fail

### FR3: Structured proposal generation
Type: functional
Priority: high
Source clauses: [C4, C5, C6, C7, C8]
Description: The investigation produces a structured list of proposed backlog items. Each proposal must include: (a) a proposed type — either "defect" or "enhancement"; (b) a title; (c) a description with evidence drawn from the investigation findings; and (d) a severity/priority suggestion.
Acceptance Criteria:
- Does each proposal include a proposed type (defect or enhancement)? YES = pass, NO = fail
- Does each proposal include a title? YES = pass, NO = fail
- Does each proposal include a description with evidence from the investigation? YES = pass, NO = fail
- Does each proposal include a severity/priority suggestion? YES = pass, NO = fail

### FR4: Slack proposal delivery with threading
Type: functional
Priority: high
Source clauses: [C9, C16, C17, C35]
Description: The pipeline sends a Slack message to the appropriate channel summarizing the proposals in a numbered list. The message must be posted as a thread-starting message so that the user's response can be in the same thread. Threading provides both persistence (message history) and traceability (parent/child relationship). The proposal message's thread_ts must be stored alongside the proposal set so the poller can match a reply to its parent proposal.
Acceptance Criteria:
- Does the pipeline send a Slack message with proposals in a numbered list? YES = pass, NO = fail
- Is the message sent to the appropriate Slack channel? YES = pass, NO = fail
- Is the proposal message a thread-starting message that supports threaded replies? YES = pass, NO = fail
- Is the thread_ts of the proposal message stored with the proposal set? YES = pass, NO = fail

### FR5: Proposal state persistence
Type: functional
Priority: high
Source clauses: [C12, C13, C14, C15, C17, C34, C38]
Description: Proposals must be persisted (not just held in memory) so that when the Slack poller receives the user's response — potentially in a later pipeline run — it can look up the most recent proposal set for that investigation. The pipeline processes items asynchronously across multiple runs, so in-memory state is insufficient. Storage options include: (a) a structured YAML/JSON file in the workspace keyed by investigation slug; (b) a proposals table in the traces DB; or (c) a file in a known location (e.g., tmp/proposals/{slug}.yaml). The stored proposal set must include the thread_ts for Slack thread matching.
Acceptance Criteria:
- Are proposals persisted to durable storage (not just in-memory)? YES = pass, NO = fail
- Can the Slack poller look up the most recent proposal set for a given investigation? YES = pass, NO = fail
- Does the persisted proposal set include the Slack thread_ts? YES = pass, NO = fail
- Do proposals survive across multiple asynchronous pipeline runs? YES = pass, NO = fail

### FR6: Flexible response parsing
Type: functional
Priority: high
Source clauses: [C18, C19, C20, C21, C22, C23, C36, C37]
Description: The system must parse the user's Slack reply to determine which proposals are accepted or rejected. Supported formats: (a) "all" or "yes" accepts everything; (b) "none" or "no" rejects everything; (c) comma-separated numbers like "1, 3, 5" accept by number; (d) "all except 2" accepts with exclusions; (e) free-text replies like "do the first three but skip the last one" are handled by an LLM call. Users will not consistently format their replies in a rigid format, so the parser must be flexible and forgiving.
Acceptance Criteria:
- Does "all" or "yes" accept all proposals? YES = pass, NO = fail
- Does "none" or "no" reject all proposals? YES = pass, NO = fail
- Does "1, 3, 5" accept exactly proposals 1, 3, and 5? YES = pass, NO = fail
- Does "all except 2" accept all proposals except number 2? YES = pass, NO = fail
- Are free-text replies parsed via an LLM call to determine accepted proposals? YES = pass, NO = fail

### FR7: Backlog filing of accepted proposals
Type: functional
Priority: high
Source clauses: [C11, C24, C29, C33, C39, C43]
Description: Accepted proposals are written as markdown files to the appropriate backlog directory — docs/defect-backlog/ for defects or docs/feature-backlog/ for enhancements — using the same format as manually created items. Backlog files are the single source of truth for pipeline work, so persisting accepted proposals as backlog entries ensures they are durable, trackable, and automatically picked up by the next pipeline cycle. Accepted items feed back into the pipeline as new work items without requiring manual backlog entry creation.
Acceptance Criteria:
- Are accepted defect proposals written to docs/defect-backlog/ as markdown files? YES = pass, NO = fail
- Are accepted enhancement proposals written to docs/feature-backlog/ as markdown files? YES = pass, NO = fail
- Do the filed items use the same format as manually created backlog items? YES = pass, NO = fail
- Are filed items automatically picked up by subsequent pipeline cycles? YES = pass, NO = fail

### FR8: Investigation workspace outcome tracking
Type: functional
Priority: medium
Source clauses: [C25, C40, C41]
Description: The investigation workspace must record the outcome of the approval process — specifically, which proposals were accepted and which were rejected. This provides full traceability of the investigation-to-backlog pipeline and enables lightweight, Slack-driven workflow without context-switching.
Acceptance Criteria:
- Does the investigation workspace record which proposals were accepted? YES = pass, NO = fail
- Does the investigation workspace record which proposals were rejected? YES = pass, NO = fail

---

## Coverage Matrix
| Raw Input Section | Requirement(s) |
|---|---|
| "Create a new pipeline workflow type 'investigation'..." (intro paragraph) | FR1 |
| Step 1: User submits investigation request | UC1 |
| Step 2: Pipeline runs the investigation | FR2 |
| Step 3: Investigation produces structured list (type, title, description, severity) | FR3 |
| Step 4: Pipeline sends Slack message with numbered list | FR4 |
| Step 5: User replies indicating which proposals to accept | UC2 |
| Step 6: Pipeline parses response, matches to proposal set, files accepted items | FR6, FR7 |
| Proposal state persistence section | FR5 |
| Slack message threading section | FR4 |
| Response parsing section (all formats) | FR6 |
| Filing accepted items section | FR7, FR8 |
| Relationship to existing analysis workflow section | FR1 |
| 5 Whys: W1 (discovery fragmentation) | UC1 |
| 5 Whys: W2 (auto-filing, not manual) | FR7, UC2 |
| 5 Whys: W3 (Slack threading for persistence/traceability) | FR4, FR5 |
| 5 Whys: W4 (flexible response formats) | FR6 |
| 5 Whys: W5 (durable backlog files) | FR5, FR7 |
| Root Need statement | FR8 |

## Clause Coverage Grid
| Clause | Type | Mapped To | Status |
|---|---|---|---|
| C1 | GOAL | FR1 | Mapped |
| C2 | GOAL | UC1 | Mapped |
| C3 | GOAL | FR2 | Mapped |
| C4 | GOAL | FR3 | Mapped |
| C5 | CONS | FR3 | Mapped |
| C6 | CONS | FR3 | Mapped |
| C7 | CONS | FR3 | Mapped |
| C8 | CONS | FR3 | Mapped |
| C9 | GOAL | FR4 | Mapped |
| C10 | GOAL | UC2 | Mapped |
| C11 | GOAL | FR7 | Mapped |
| C12 | CONS | FR5 | Mapped |
| C13 | CONS | FR5 | Mapped |
| C14 | CONS | FR5 | Mapped |
| C15 | CONS | FR5 | Mapped |
| C16 | CONS | FR4 | Mapped |
| C17 | CONS | FR4, FR5 | Mapped |
| C18 | CONS | FR6 | Mapped |
| C19 | CONS | FR6 | Mapped |
| C20 | CONS | FR6 | Mapped |
| C21 | CONS | FR6 | Mapped |
| C22 | CONS | FR6 | Mapped |
| C23 | CONS | FR6 | Mapped |
| C24 | CONS | FR7 | Mapped |
| C25 | CONS | FR8 | Mapped |
| C26 | FACT | FR1 | Mapped (contrast with existing analysis) |
| C27 | CONS | FR1 | Mapped |
| C28 | CONS | UC2 | Mapped |
| C29 | CONS | FR7 | Mapped |
| C30 | CONS | FR1 | Mapped |
| C31 | GOAL | UC1, FR2 | Mapped |
| C32 | CONS | UC2 | Mapped |
| C33 | CONS | FR7 | Mapped |
| C34 | CONS | FR5 | Mapped |
| C35 | CONS | FR4 | Mapped |
| C36 | FACT | FR6 | Mapped (motivates flexible parsing) |
| C37 | GOAL | FR6 | Mapped |
| C38 | FACT | FR5 | Mapped (motivates persistence across runs) |
| C39 | GOAL | FR7 | Mapped |
| C40 | GOAL | FR8 | Mapped |
| C41 | GOAL | FR8 | Mapped |
| C42 | CTX | UC1 | Mapped (context for investigation motivation) |
| C43 | FACT | FR7 | Mapped (backlog files as single source of truth) |

## Validation

Status: ACCEPTED
Iterations: 1
Reviewer notes: Reviewer unavailable (iteration 1): quota_exhausted
