# Structured Requirements: 82 Investigation Workflow With Slack Proposals

Source: tmp/plans/.claimed/82-investigation-workflow-with-slack-proposals.md
Generated: 2026-04-02T18:28:36.576281+00:00

## Requirements

Looking at the reviewer's feedback: P1 describes a system capability (parsing variable input formats), not a broken thing in an existing system. Since the system doesn't exist yet, "users won't consistently format replies" is a design constraint driving FR5 and UC3, not a problem to fix. I'll remove P1 and remap its clauses (C40, C41) to the functional requirements that already cover this behavior.

---

### UC1: Submit an investigation request
Type: functional
Priority: high
Source clauses: [C1, C2, C34]
Description: A user submits an investigation request describing a symptom or area of the codebase to analyze (e.g. "investigate why item 74 has two dashboard entries and incomplete tasks"). The system accepts this as a new pipeline work item of type "investigation" and begins processing it. This enables users to systematically analyze symptoms and identify root causes rather than discovering related issues ad-hoc.
Acceptance Criteria:
- Can the user submit a free-text investigation request that the pipeline accepts as type "investigation"? YES = pass, NO = fail
- Does the pipeline distinguish an investigation request from other workflow types (feature, defect, analysis)? YES = pass, NO = fail

---

### UC2: Review proposals and approve via Slack thread
Type: functional
Priority: high
Source clauses: [C10, C30, C36, C46]
Description: After the pipeline produces investigation proposals, the user reviews the numbered list in a Slack message and replies in the same thread indicating which proposals to accept. The human-in-the-loop approval must happen in-context via the Slack thread before any items are filed. This enables lightweight, Slack-driven approval without context-switching.
Acceptance Criteria:
- Does the user receive a numbered list of proposals in a Slack message they can reply to? YES = pass, NO = fail
- Can the user reply in the thread to approve, reject, or selectively accept proposals? YES = pass, NO = fail
- Is the approval step required before any backlog items are filed? YES = pass, NO = fail

---

### UC3: Respond to proposals using flexible formats
Type: functional
Priority: high
Source clauses: [C20, C21, C22, C23, C24, C40, C41, C42]
Description: The user can reply to the proposal Slack message using any reasonable format to indicate their approval decisions. Supported formats include: "all" or "yes" to accept everything; "none" or "no" to reject everything; "1, 3, 5" to accept by number; "all except 2" to accept with exclusions; and free-text replies like "do the first three but skip the last one" which are handled by an LLM call. Users will not consistently format their replies, so accepting any reasonable format reduces friction and user error. A malformed or ambiguous response must result in a graceful fallback (e.g. LLM interpretation or clarification request) rather than silent failure.
Acceptance Criteria:
- Does "all" or "yes" accept all proposals? YES = pass, NO = fail
- Does "none" or "no" reject all proposals? YES = pass, NO = fail
- Does "1, 3, 5" accept exactly proposals 1, 3, and 5? YES = pass, NO = fail
- Does "all except 2" accept all proposals except number 2? YES = pass, NO = fail
- Does a free-text reply like "do the first three but skip the last one" get correctly interpreted via an LLM call? YES = pass, NO = fail
- Does a malformed or ambiguous response result in a graceful fallback rather than silent failure? YES = pass, NO = fail

---

### FR1: Investigation workflow type in the pipeline
Type: functional
Priority: high
Source clauses: [C1, C3, C29, C32, C33]
Description: Create a new pipeline workflow type "investigation" that reads relevant code, logs, data, and traces to identify root causes for a reported symptom or codebase area. Unlike the existing analysis workflow which produces a single analysis document, the investigation workflow produces multiple discrete actionable items. The investigation may reuse the analysis intake (clause extraction, 5 whys) for the initial request, but the output stage is entirely different.
Acceptance Criteria:
- Does the pipeline recognize and route "investigation" as a distinct workflow type? YES = pass, NO = fail
- Does the investigation read relevant code, logs, data, and traces during execution? YES = pass, NO = fail
- Does the investigation produce multiple discrete items rather than a single document? YES = pass, NO = fail
- Can the investigation reuse the analysis intake (clause extraction, 5 whys) for its initial request? YES = pass, NO = fail

---

### FR2: Structured proposal generation
Type: functional
Priority: high
Source clauses: [C4, C5, C6, C7, C8]
Description: The investigation produces a structured list of proposed backlog items. Each proposal must include: a proposed type (defect or enhancement), a title, a description with evidence from the investigation, and a severity/priority suggestion.
Acceptance Criteria:
- Does each proposal include a type field set to either "defect" or "enhancement"? YES = pass, NO = fail
- Does each proposal include a title? YES = pass, NO = fail
- Does each proposal include a description with evidence from the investigation? YES = pass, NO = fail
- Does each proposal include a severity/priority suggestion? YES = pass, NO = fail

---

### FR3: Slack proposal messaging with threading
Type: functional
Priority: high
Source clauses: [C9, C17, C18, C19, C39]
Description: The pipeline sends a Slack message to the appropriate channel summarizing the proposals in a numbered list. The proposal message and the user's response must be in a thread so the poller can match a reply to its parent proposal message. The proposal message's thread_ts must be stored with the proposal set to enable this matching. Threading provides both persistence (message history) and traceability (parent/child relationship).
Acceptance Criteria:
- Does the pipeline send a numbered proposal list to the appropriate Slack channel? YES = pass, NO = fail
- Is the proposal sent as a threaded message (or does it initiate a thread)? YES = pass, NO = fail
- Is the proposal message's thread_ts stored with the proposal set? YES = pass, NO = fail
- Can the Slack poller match a user reply to its parent proposal message via thread_ts? YES = pass, NO = fail

---

### FR4: Proposal state persistence
Type: functional
Priority: high
Source clauses: [C12, C13, C14, C15, C16, C38, C43]
Description: Proposals must be persisted (not just held in memory) so that when the Slack poller receives the user's response, it can look up the most recent proposal set for that conversation. The pipeline processes items asynchronously across multiple runs, so in-memory state is insufficient. Storage options to evaluate include: a structured YAML/JSON file in the workspace keyed by investigation slug, a proposals table in the traces DB, or a file in a known location (e.g. tmp/proposals/{slug}.yaml). The design must select and implement one of these options.
Acceptance Criteria:
- Are proposals persisted to durable storage (not just in-memory)? YES = pass, NO = fail
- Can the Slack poller look up the most recent proposal set for a given investigation after a process restart? YES = pass, NO = fail
- Is the proposal set keyed or indexed so it can be matched to a specific investigation? YES = pass, NO = fail

---

### FR5: Response parsing and proposal matching
Type: functional
Priority: high
Source clauses: [C11, C13, C24, C40, C41]
Description: The pipeline parses the user's Slack response and matches it to the most recent proposal set for that investigation. Parsing must handle structured formats (numbered lists, "all", "none", "all except N") via deterministic logic and fall back to an LLM call for free-text replies that don't match structured patterns. The parser must resolve the response to a concrete set of accepted and rejected proposal numbers. Because users will not consistently format their replies, the parser must be robust against varied and informal input.
Acceptance Criteria:
- Does the parser resolve structured formats without an LLM call? YES = pass, NO = fail
- Does the parser fall back to an LLM call for unrecognized free-text? YES = pass, NO = fail
- Does the parser match the response to the correct proposal set for that investigation? YES = pass, NO = fail
- Does the parser produce an explicit list of accepted and rejected proposal indices? YES = pass, NO = fail

---

### FR6: File accepted proposals as backlog items
Type: functional
Priority: high
Source clauses: [C25, C26, C27, C44]
Description: Accepted proposals are written as markdown files to the appropriate backlog directory (docs/defect-backlog/ for defects, docs/feature-backlog/ for enhancements) using the same format as manually created items. The investigation workspace must also record which proposals were accepted and which were rejected. Persisting proposals as backlog entries ensures they are durable, trackable, and automatically picked up by the next pipeline cycle.
Acceptance Criteria:
- Are accepted defect proposals written to docs/defect-backlog/ as markdown files? YES = pass, NO = fail
- Are accepted enhancement proposals written to docs/feature-backlog/ as markdown files? YES = pass, NO = fail
- Do the filed items use the same format as manually created backlog items? YES = pass, NO = fail
- Does the investigation workspace record which proposals were accepted and which were rejected? YES = pass, NO = fail

---

### FR7: Accepted items feed back into the pipeline
Type: functional
Priority: high
Source clauses: [C31, C37, C47, C48, C49]
Description: Accepted items must automatically feed back into the pipeline as new work items rather than requiring manual backlog entry creation. Because filed items are written to the standard backlog directories, they are automatically picked up by the next pipeline intake cycle. Investigation results become backlog work items with minimal manual overhead and full traceability.
Acceptance Criteria:
- Are filed backlog items automatically discovered by the pipeline's next intake cycle? YES = pass, NO = fail
- Does the pipeline process filed investigation outputs the same way it processes manually created backlog items? YES = pass, NO = fail
- Is no manual intervention required between filing and pipeline pickup? YES = pass, NO = fail

---

## Coverage Matrix

| Raw Input Section | Requirement(s) |
|---|---|
| "Create a new pipeline workflow type 'investigation'..." (intro paragraph) | FR1, UC1 |
| "User submits an investigation request" (step 1) | UC1 |
| "Pipeline runs the investigation: reads relevant code, logs, data, and traces" (step 2) | FR1 |
| "Investigation produces a structured list of proposed backlog items" (step 3, including sub-bullets) | FR2 |
| "Pipeline sends a Slack message...summarizing the proposals in a numbered list" (step 4) | FR3 |
| "User replies to the Slack message indicating which proposals to accept" (step 5) | UC2, UC3 |
| "Pipeline parses the user's response, matches it...and files the accepted items" (step 6) | FR5, FR6 |
| "Proposal state persistence" section | FR4 |
| "Slack message threading" section | FR3 |
| "Response parsing" section (all format examples) | UC3, FR5 |
| "Filing accepted items" section | FR6, FR7 |
| "Relationship to existing analysis workflow" section | FR1, FR7 |
| "5 Whys Analysis" W1 (discovery fragmentation) | UC1 |
| "5 Whys Analysis" W2 (manual filing overhead) | FR7 |
| "5 Whys Analysis" W3 (Slack threading for persistence/traceability) | FR3 |
| "5 Whys Analysis" W4 (inconsistent reply formats) | UC3, FR5 |
| "5 Whys Analysis" W5 (async persistence across runs) | FR4, FR6 |
| Root Need statement | UC2, FR7 |

## Clause Coverage Grid

| Clause | Type | Mapped To | Status |
|---|---|---|---|
| C1 [GOAL] | GOAL | FR1, UC1 | Mapped |
| C2 [GOAL] | GOAL | UC1 | Mapped |
| C3 [GOAL] | GOAL | FR1 | Mapped |
| C4 [GOAL] | GOAL | FR2 | Mapped |
| C5 [GOAL] | GOAL | FR2 | Mapped |
| C6 [GOAL] | GOAL | FR2 | Mapped |
| C7 [GOAL] | GOAL | FR2 | Mapped |
| C8 [GOAL] | GOAL | FR2 | Mapped |
| C9 [GOAL] | GOAL | FR3 | Mapped |
| C10 [GOAL] | GOAL | UC2 | Mapped |
| C11 [GOAL] | GOAL | FR5 | Mapped |
| C12 [CONS] | CONS | FR4 | Mapped |
| C13 [CONS] | CONS | FR4, FR5 | Mapped |
| C14 [GOAL] | GOAL | FR4 | Mapped |
| C15 [GOAL] | GOAL | FR4 | Mapped |
| C16 [GOAL] | GOAL | FR4 | Mapped |
| C17 [CONS] | CONS | FR3 | Mapped |
| C18 [CONS] | CONS | FR3 | Mapped |
| C19 [CONS] | CONS | FR3 | Mapped |
| C20 [GOAL] | GOAL | UC3 | Mapped |
| C21 [GOAL] | GOAL | UC3 | Mapped |
| C22 [GOAL] | GOAL | UC3 | Mapped |
| C23 [GOAL] | GOAL | UC3 | Mapped |
| C24 [GOAL] | GOAL | UC3, FR5 | Mapped |
| C25 [GOAL] | GOAL | FR6 | Mapped |
| C26 [CONS] | CONS | FR6 | Mapped |
| C27 [GOAL] | GOAL | FR6 | Mapped |
| C28 [FACT] | FACT | -- | Unmapped: context establishing how the existing analysis workflow works; referenced by FR1's differentiation |
| C29 [GOAL] | GOAL | FR1 | Mapped |
| C30 [GOAL] | GOAL | UC2 | Mapped |
| C31 [GOAL] | GOAL | FR7 | Mapped |
| C32 [GOAL] | GOAL | FR1 | Mapped |
| C33 [CTX] | CTX | -- | Unmapped: context clarifying that the output stage differs from analysis; captured in FR1 description |
| C34 [GOAL] | GOAL | UC1 | Mapped |
| C35 [CTX] | CTX | -- | Unmapped: assumption annotation on discovery fragmentation; motivational context for UC1 |
| C36 [CONS] | CONS | UC2 | Mapped |
| C37 [GOAL] | GOAL | FR7 | Mapped |
| C38 [CONS] | CONS | FR4 | Mapped |
| C39 [CTX] | CTX | -- | Unmapped: context explaining why threading is valuable; captured in FR3 description |
| C40 [PROB] | PROB | UC3, FR5 | Mapped (as design constraint driving flexible parsing, not as a standalone problem requirement) |
| C41 [FACT] | FACT | UC3, FR5 | Mapped (factual basis for flexible parsing requirement) |
| C42 [GOAL] | GOAL | UC3 | Mapped |
| C43 [FACT] | FACT | FR4 | Mapped |
| C44 [GOAL] | GOAL | FR6 | Mapped |
| C45 [CTX] | CTX | -- | Unmapped: assumption annotation that backlog files are single source of truth; motivational context for FR6/FR7 |
| C46 [GOAL] | GOAL | UC2 | Mapped |
| C47 [GOAL] | GOAL | FR7 | Mapped |
| C48 [GOAL] | GOAL | FR7 | Mapped |
| C49 [GOAL] | GOAL | FR7 | Mapped |

---

**Changes made:**

1. **Removed P1** -- The "inconsistent user response formats" issue is not a broken thing in an existing system; it's a design constraint for a system that doesn't exist yet. The content (flexible parsing, graceful fallback) is a capability requirement, not a problem statement.

2. **Absorbed P1's content into UC3 and FR5** -- UC3 now includes the graceful fallback acceptance criterion that was unique to P1, and FR5's description now explicitly notes the robustness requirement driven by inconsistent user input. No information was lost.

3. **Remapped C40 [PROB] and C41 [FACT]** -- These clauses now map to UC3 and FR5, with a note in the grid explaining they serve as the design constraint driving the flexible parsing capability rather than standing alone as a problem requirement.

## Validation

Status: ACCEPTED
Iterations: 2
Reviewer notes: ACCEPT


## Acceptance Criteria

**AC1**: Can the user submit a free-text investigation request that the pipeline accepts as a new work item of type "investigation"? YES = pass, NO = fail
  Origin: Derived from C1 [GOAL] (operationalized) + Derived from C2 [GOAL] (operationalized)
  Belongs to: UC1
  Source clauses: [C1, C2]

**AC2**: Does the pipeline distinguish an "investigation" workflow type from other workflow types (feature, defect, analysis) during routing? YES = pass, NO = fail
  Origin: Derived from C1 [GOAL] (operationalized)
  Belongs to: UC1
  Source clauses: [C1]

**AC3**: Does the investigation workflow enable systematic analysis of a reported symptom or codebase area to identify root causes, rather than requiring ad-hoc discovery? YES = pass, NO = fail
  Origin: Derived from C34 [GOAL] (operationalized)
  Belongs to: UC1
  Source clauses: [C34]

**AC4**: Does the user receive a numbered list of proposals in a Slack message they can reply to? YES = pass, NO = fail
  Origin: Derived from C10 [GOAL] (operationalized)
  Belongs to: UC2
  Source clauses: [C10]

**AC5**: Is a human-in-the-loop approval step required in-context via the Slack thread before any backlog items are filed? YES = pass, NO = fail
  Origin: Derived from C30 [GOAL] (operationalized) + Derived from C36 [CONS] (made testable)
  Belongs to: UC2
  Source clauses: [C30, C36]

**AC6**: Can the user complete the entire investigation-to-approval flow via Slack without context-switching to another tool? YES = pass, NO = fail
  Origin: Derived from C46 [GOAL] (operationalized)
  Belongs to: UC2
  Source clauses: [C46]

**AC7**: Does replying "all" or "yes" accept all proposals? YES = pass, NO = fail
  Origin: Derived from C20 [GOAL] (operationalized)
  Belongs to: UC3
  Source clauses: [C20]

**AC8**: Does replying "none" or "no" reject all proposals? YES = pass, NO = fail
  Origin: Derived from C21 [GOAL] (operationalized)
  Belongs to: UC3
  Source clauses: [C21]

**AC9**: Does replying "1, 3, 5" accept exactly proposals 1, 3, and 5 and reject the rest? YES = pass, NO = fail
  Origin: Derived from C22 [GOAL] (operationalized)
  Belongs to: UC3
  Source clauses: [C22]

**AC10**: Does replying "all except 2" accept all proposals except number 2? YES = pass, NO = fail
  Origin: Derived from C23 [GOAL] (operationalized)
  Belongs to: UC3
  Source clauses: [C23]

**AC11**: Does a free-text reply like "do the first three but skip the last one" get correctly interpreted via an LLM call? YES = pass, NO = fail
  Origin: Derived from C24 [GOAL] (operationalized)
  Belongs to: UC3
  Source clauses: [C24]

**AC12**: Does a malformed or ambiguous response result in a graceful fallback (LLM interpretation or clarification request) rather than silent failure or data loss? YES = pass, NO = fail
  Origin: Derived from C40 [PROB] (inverse) + Derived from C42 [GOAL] (operationalized)
  Belongs to: UC3
  Source clauses: [C40, C42]

**AC13**: Does the pipeline recognize and route "investigation" as a distinct workflow type separate from existing types? YES = pass, NO = fail
  Origin: Derived from C1 [GOAL] (operationalized)
  Belongs to: FR1
  Source clauses: [C1]

**AC14**: Does the investigation workflow read relevant code, logs, data, and traces during execution to identify root causes? YES = pass, NO = fail
  Origin: Derived from C3 [GOAL] (operationalized)
  Belongs to: FR1
  Source clauses: [C3]

**AC15**: Does the investigation produce multiple discrete actionable items rather than a single analysis document? YES = pass, NO = fail
  Origin: Derived from C29 [GOAL] (operationalized)
  Belongs to: FR1
  Source clauses: [C29]

**AC16**: Can the investigation reuse the analysis intake stage (clause extraction, 5 whys) for its initial request processing? YES = pass, NO = fail
  Origin: Derived from C32 [GOAL] (operationalized)
  Belongs to: FR1
  Source clauses: [C32]

**AC17**: Does each proposal include a type field set to either "defect" or "enhancement"? YES = pass, NO = fail
  Origin: Derived from C5 [GOAL] (operationalized)
  Belongs to: FR2
  Source clauses: [C4, C5]

**AC18**: Does each proposal include a title? YES = pass, NO = fail
  Origin: Derived from C6 [GOAL] (operationalized)
  Belongs to: FR2
  Source clauses: [C4, C6]

**AC19**: Does each proposal include a description containing evidence from the investigation? YES = pass, NO = fail
  Origin: Derived from C7 [GOAL] (operationalized)
  Belongs to: FR2
  Source clauses: [C4, C7]

**AC20**: Does each proposal include a severity/priority suggestion? YES = pass, NO = fail
  Origin: Derived from C8 [GOAL] (operationalized)
  Belongs to: FR2
  Source clauses: [C4, C8]

**AC21**: Does the pipeline send a numbered proposal summary list to the appropriate Slack channel? YES = pass, NO = fail
  Origin: Derived from C9 [GOAL] (operationalized)
  Belongs to: FR3
  Source clauses: [C9]

**AC22**: Is the proposal message sent as a thread-initiating message (or within a thread) so that user replies are threaded? YES = pass, NO = fail
  Origin: Derived from C17 [CONS] (made testable)
  Belongs to: FR3
  Source clauses: [C17, C18]

**AC23**: Is the proposal message's thread_ts stored with the proposal set? YES = pass, NO = fail
  Origin: Derived from C19 [CONS] (made testable)
  Belongs to: FR3
  Source clauses: [C19]

**AC24**: Can the Slack poller match a user's thread reply to its parent proposal message via thread_ts? YES = pass, NO = fail
  Origin: Derived from C18 [CONS] (made testable)
  Belongs to: FR3
  Source clauses: [C17, C18]

**AC25**: Are proposals persisted to durable storage (not just held in memory)? YES = pass, NO = fail
  Origin: Derived from C12 [CONS] (made testable)
  Belongs to: FR4
  Source clauses: [C12, C38]

**AC26**: Can the Slack poller look up the most recent proposal set for a given investigation after a process restart? YES = pass, NO = fail
  Origin: Derived from C13 [CONS] (made testable)
  Belongs to: FR4
  Source clauses: [C13, C43]

**AC27**: Is the proposal set keyed or indexed by investigation slug so it can be matched to a specific investigation? YES = pass, NO = fail
  Origin: Derived from C14 [GOAL] (operationalized)
  Belongs to: FR4
  Source clauses: [C14]

**AC28**: Is the proposal storage implemented using at least one of: a structured YAML/JSON file keyed by slug, a proposals table in the traces DB, or a file in tmp/proposals/{slug}.yaml? YES = pass, NO = fail
  Origin: Derived from C15 [GOAL] (operationalized) + Derived from C16 [GOAL] (operationalized)
  Belongs to: FR4
  Source clauses: [C14, C15, C16]

**AC29**: Does the parser resolve structured formats ("all", "none", "1,3,5", "all except 2") deterministically without an LLM call? YES = pass, NO = fail
  Origin: Derived from C11 [GOAL] (operationalized)
  Belongs to: FR5
  Source clauses: [C11]

**AC30**: Does the parser fall back to an LLM call for free-text replies that do not match any structured pattern? YES = pass, NO = fail
  Origin: Derived from C24 [GOAL] (operationalized)
  Belongs to: FR5
  Source clauses: [C24]

**AC31**: Does the parser match the user's response to the correct proposal set for that investigation (using the persisted proposal set and thread_ts)? YES = pass, NO = fail
  Origin: Derived from C13 [CONS] (made testable) + Derived from C11 [GOAL] (operationalized)
  Belongs to: FR5
  Source clauses: [C11, C13]

**AC32**: Does the parser produce an explicit list of accepted and rejected proposal indices as its output? YES = pass, NO = fail
  Origin: Derived from C11 [GOAL] (operationalized)
  Belongs to: FR5
  Source clauses: [C11]

**AC33**: Are accepted defect proposals written as markdown files to docs/defect-backlog/? YES = pass, NO = fail
  Origin: Derived from C25 [GOAL] (operationalized)
  Belongs to: FR6
  Source clauses: [C25]

**AC34**: Are accepted enhancement proposals written as markdown files to docs/feature-backlog/? YES = pass, NO = fail
  Origin: Derived from C25 [GOAL] (operationalized)
  Belongs to: FR6
  Source clauses: [C25]

**AC35**: Do the filed backlog items use the same markdown format as manually created backlog items? YES = pass, NO = fail
  Origin: Derived from C26 [CONS] (made testable)
  Belongs to: FR6
  Source clauses: [C26]

**AC36**: Does the investigation workspace record which proposals were accepted and which were rejected? YES = pass, NO = fail
  Origin: Derived from C27 [GOAL] (operationalized)
  Belongs to: FR6
  Source clauses: [C27]

**AC37**: Are accepted proposals persisted as backlog entries that are durable and trackable across pipeline runs? YES = pass, NO = fail
  Origin: Derived from C44 [GOAL] (operationalized)
  Belongs to: FR6
  Source clauses: [C44]

**AC38**: Are filed backlog items automatically discovered by the pipeline's next intake cycle without manual intervention? YES = pass, NO = fail
  Origin: Derived from C31 [GOAL] (operationalized) + Derived from C37 [GOAL] (operationalized)
  Belongs to: FR7
  Source clauses: [C31, C37]

**AC39**: Does the pipeline process filed investigation outputs the same way it processes manually created backlog items? YES = pass, NO = fail
  Origin: Derived from C37 [GOAL] (operationalized)
  Belongs to: FR7
  Source clauses: [C37]

**AC40**: Is no manual intervention required between filing accepted proposals and the pipeline picking them up as work items? YES = pass, NO = fail
  Origin: Derived from C47 [GOAL] (operationalized) + Derived from C48 [GOAL] (operationalized)
  Belongs to: FR7
  Source clauses: [C47, C48]

**AC41**: Do investigation results become backlog work items with full traceability back to the originating investigation? YES = pass, NO = fail
  Origin: Derived from C49 [GOAL] (operationalized) + Derived from C47 [GOAL] (operationalized)
  Belongs to: FR7
  Source clauses: [C47, C49]

---

## Requirement -> AC Coverage

| Requirement | ACs | Count |
|---|---|---|
| UC1 | AC1, AC2, AC3 | 3 |
| UC2 | AC4, AC5, AC6 | 3 |
| UC3 | AC7, AC8, AC9, AC10, AC11, AC12 | 6 |
| FR1 | AC13, AC14, AC15, AC16 | 4 |
| FR2 | AC17, AC18, AC19, AC20 | 4 |
| FR3 | AC21, AC22, AC23, AC24 | 4 |
| FR4 | AC25, AC26, AC27, AC28 | 4 |
| FR5 | AC29, AC30, AC31, AC32 | 4 |
| FR6 | AC33, AC34, AC35, AC36, AC37 | 5 |
| FR7 | AC38, AC39, AC40, AC41 | 4 |

---

## Clause -> AC Coverage

| Clause | Type | AC | How |
|---|---|---|---|
| C1 | GOAL | AC1, AC2, AC13 | Made testable |
| C2 | GOAL | AC1 | Made testable |
| C3 | GOAL | AC14 | Made testable |
| C4 | GOAL | AC17, AC18, AC19, AC20 | Made testable (via sub-clauses C5-C8) |
| C5 | GOAL | AC17 | Made testable |
| C6 | GOAL | AC18 | Made testable |
| C7 | GOAL | AC19 | Made testable |
| C8 | GOAL | AC20 | Made testable |
| C9 | GOAL | AC21 | Made testable |
| C10 | GOAL | AC4 | Made testable |
| C11 | GOAL | AC29, AC31, AC32 | Made testable |
| C12 | CONS | AC25 | Made testable |
| C13 | CONS | AC26, AC31 | Made testable |
| C14 | GOAL | AC27, AC28 | Made testable |
| C15 | GOAL | AC28 | Made testable |
| C16 | GOAL | AC28 | Made testable |
| C17 | CONS | AC22, AC24 | Made testable |
| C18 | CONS | AC22, AC24 | Made testable |
| C19 | CONS | AC23 | Made testable |
| C20 | GOAL | AC7 | Made testable |
| C21 | GOAL | AC8 | Made testable |
| C22 | GOAL | AC9 | Made testable |
| C23 | GOAL | AC10 | Made testable |
| C24 | GOAL | AC11, AC30 | Made testable |
| C25 | GOAL | AC33, AC34 | Made testable |
| C26 | CONS | AC35 | Made testable |
| C27 | GOAL | AC36 | Made testable |
| C28 | FACT | -- | Context: establishes how the existing analysis workflow works (single document output); referenced by FR1/AC15 as the behavior to differentiate from, but not independently testable |
| C29 | GOAL | AC15 | Made testable |
| C30 | GOAL | AC5 | Made testable |
| C31 | GOAL | AC38 | Made testable |
| C32 | GOAL | AC16 | Made testable |
| C33 | CTX | -- | Context: clarifies that the investigation output stage differs from analysis; captured in FR1 description and implicitly verified by AC15 |
| C34 | GOAL | AC3 | Made testable |
| C35 | CTX | -- | Assumption annotation: "root problem is discovery fragmentation"; motivational context for UC1, not independently testable |
| C36 | CONS | AC5 | Made testable |
| C37 | GOAL | AC38, AC39 | Made testable |
| C38 | CONS | AC25 | Made testable |
| C39 | CTX | -- | Context: explains why threading provides persistence and traceability; rationale for FR3 design, verified indirectly by AC22-AC24 |
| C40 | PROB | AC12 | Inverse: "users won't format consistently" -> "does the system handle inconsistent formats gracefully?" |
| C41 | FACT | -- | Factual basis: enumerates the variety of user reply formats; drives the specific test cases in AC7-AC11 rather than being independently testable |
| C42 | GOAL | AC12 | Made testable |
| C43 | FACT | -- | Factual basis: pipeline processes items asynchronously across runs; drives the persistence requirement verified by AC25-AC26 rather than being independently testable |
| C44 | GOAL | AC37 | Made testable |
| C45 | CTX | -- | Assumption annotation: "backlog files are single source of truth for pipeline work"; architectural context for FR6/FR7, verified indirectly by AC38-AC39 |
| C46 | GOAL | AC6 | Made testable |
| C47 | GOAL | AC40, AC41 | Made testable |
| C48 | GOAL | AC40 | Made testable |
| C49 | GOAL | AC41 | Made testable |

---

## Coverage Summary

- **41 acceptance criteria** across **10 requirements**
- **All 33 GOAL clauses**: covered (each has at least one AC)
- **All 8 CONS clauses**: covered (each has at least one AC)
- **1 PROB clause (C40)**: covered via AC12 (inverse)
- **3 FACT clauses (C28, C41, C43)**: justified as contextual/factual basis driving other ACs, not independently testable
- **4 CTX clauses (C33, C35, C39, C45)**: justified as motivational/architectural context, not independently testable
- **No orphan requirements**: every UC and FR has 3-6 ACs
- **No orphan GOAL/CONS/PROB clauses**: full clause coverage
