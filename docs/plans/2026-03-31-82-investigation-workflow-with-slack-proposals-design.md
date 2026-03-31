# Design: 82 Investigation Workflow With Slack Proposals

Source item: tmp/plans/.claimed/82-investigation-workflow-with-slack-proposals.md
Requirements: docs/plans/2026-03-31-82-investigation-workflow-with-slack-proposals-requirements.md

## Architecture Overview

The investigation workflow adds a new pipeline path that diverges from the standard
defect/feature flow after the intake node. Instead of structuring requirements and
creating an execution plan, investigations run a Claude-driven analysis that produces
multiple discrete proposals, posts them to Slack for human approval, and files accepted
items as new backlog entries.

### Pipeline Flow

```
intake_analyze (reuses 5-whys for investigation)
    |
    v [route_after_intake -- investigation branch]
run_investigation (Claude analysis -> proposals YAML)
    |
    v
process_investigation (Slack post -> poll reply -> parse -> file -> record)
    |
    v [route_after_process_investigation]
archive (if done) | END (if waiting for reply)
```

### Key Files

New files:
- langgraph_pipeline/investigation/__init__.py -- module init
- langgraph_pipeline/investigation/proposals.py -- Proposal/ProposalSet models, persistence, response parser, filing
- langgraph_pipeline/pipeline/nodes/investigation.py -- run_investigation and process_investigation pipeline nodes
- tests/langgraph/investigation/__init__.py -- test module init
- tests/langgraph/investigation/test_proposals.py -- proposal model, parser, filing tests
- tests/langgraph/pipeline/nodes/test_investigation.py -- pipeline node tests

Modified files:
- langgraph_pipeline/pipeline/state.py -- add "investigation" to ItemType
- langgraph_pipeline/shared/paths.py -- add INVESTIGATION_DIR, COMPLETED_INVESTIGATIONS_DIR
- langgraph_pipeline/pipeline/edges.py -- add investigation routing functions and node constants
- langgraph_pipeline/pipeline/graph.py -- wire investigation nodes into graph
- langgraph_pipeline/pipeline/nodes/__init__.py -- export investigation nodes
- langgraph_pipeline/pipeline/nodes/intake.py -- handle investigation type (reuse 5-whys path)
- langgraph_pipeline/pipeline/nodes/archival.py -- handle investigation archival
- langgraph_pipeline/slack/notifier.py -- add investigation channel suffix, add post_proposals method
- langgraph_pipeline/supervisor.py -- scan investigation backlog directory

## Design Decisions

### D1: Add "investigation" as a new ItemType with dedicated infrastructure

Addresses: FR1, UC1
Satisfies: AC1, AC2, AC3, AC7

Approach: Add "investigation" to the ItemType literal in state.py. Add
INVESTIGATION_DIR (docs/investigation-backlog) and COMPLETED_INVESTIGATIONS_DIR
(docs/completed-backlog/investigations) to paths.py. Add these to BACKLOG_DIRS
and COMPLETED_DIRS dictionaries. Update the supervisor scan order to include
investigation items. Update the worker to accept "investigation" as an item type.

Files: state.py, paths.py, supervisor.py, worker.py

### D2: Reuse analysis intake (clause extraction, 5 whys) for investigation type

Addresses: FR1
Satisfies: AC10

Approach: In intake.py, treat investigation items the same as analysis items for
the intake phase -- run clause extraction and 5-whys analysis. The investigation
type already matches the analysis pattern of needing root-cause analysis before
proceeding. The intake output (clause_register_path, five_whys_path) feeds into
the investigation analysis node as context.

Files: intake.py

### D3: Claude-driven investigation analysis producing structured proposals

Addresses: FR2, FR3
Satisfies: AC11, AC12, AC13, AC14, AC15, AC16, AC17, AC18

Approach: Create a run_investigation pipeline node that spawns Claude (Opus) with
a structured prompt. The prompt includes the original item content, clause register,
and 5-whys output as context, and instructs Claude to: (1) read relevant code, logs,
data, and traces referenced in the analysis, (2) perform systematic root-cause
investigation, (3) output a JSON array of proposals. Each proposal has: type
(defect or enhancement), title, description with evidence citations from the
codebase, and severity (critical/high/medium/low). The node parses the JSON output,
validates each proposal has all required fields, and constructs a ProposalSet.

Files: langgraph_pipeline/pipeline/nodes/investigation.py

### D4: Proposal persistence as YAML in workspace

Addresses: FR5
Satisfies: AC24, AC25, AC26, AC27

Approach: Define Proposal and ProposalSet dataclasses in
langgraph_pipeline/investigation/proposals.py. ProposalSet contains: slug,
generated_at timestamp, status (pending/approved/rejected/partial), slack_channel_id,
slack_thread_ts (populated after posting), reply_text (populated after response),
and a list of Proposal objects. Persist as {workspace}/proposals.yaml using
PyYAML safe_dump. The file is keyed by slug implicitly (each workspace directory
corresponds to one slug). The thread_ts field enables Slack reply matching. File-based
persistence survives pipeline restarts.

Proposal dataclass fields: number (int), proposal_type (defect/enhancement), title,
description, severity, status (pending/accepted/rejected), filed_path (Optional,
set after filing).

Files: langgraph_pipeline/investigation/proposals.py

### D5: Slack numbered list delivery with thread_ts tracking

Addresses: FR4
Satisfies: AC19, AC20, AC21, AC22, AC23

Approach: Add an "investigations" channel role to SLACK_CHANNEL_ROLE_SUFFIXES in
notifier.py (maps to orchestrator-investigations channel). Add a post_proposals()
method to SlackNotifier that formats proposals as a numbered Block Kit message
with type badges, titles, descriptions, and severity. Post as a top-level message
so user replies create a thread. Capture the returned message ts (which becomes
the thread_ts for replies) and store it in the ProposalSet. The Slack poller can
then match threaded replies to the parent proposal message via the stored thread_ts.

Files: langgraph_pipeline/slack/notifier.py

### D6: Suspension-based reply polling with should_stop pattern

Addresses: UC2
Satisfies: AC4, AC5, AC6

Approach: The process_investigation node implements a state-machine pattern:
(1) If proposals are persisted but no thread_ts exists, post to Slack and set
should_stop=True. (2) If thread_ts exists but no reply, poll the Slack thread
using conversations.replies API. If no reply found, set should_stop=True (the
supervisor will re-invoke on the next cycle). (3) If a reply is found, proceed
to parse and file. This reuses the existing pipeline pattern where should_stop
causes the graph to route to END and the supervisor retries later. The human
approval gate ensures no items are filed until the user responds.

Files: langgraph_pipeline/pipeline/nodes/investigation.py

### D7: Multi-strategy response parser with LLM fallback

Addresses: FR6
Satisfies: AC28, AC29, AC30, AC31, AC32, AC33, AC34

Approach: Implement parse_approval_response(text, proposal_count) in proposals.py
that returns a set of accepted proposal numbers. Strategy chain (case-insensitive,
whitespace-stripped):
1. "all" or "yes" -> accept all (numbers 1..proposal_count)
2. "none" or "no" -> accept none (empty set)
3. Regex for comma/space-separated numbers (e.g. "1, 3, 5") -> accept listed
4. Regex for "all except N[, M...]" -> accept all minus listed
5. Fallback: call Claude (Haiku for cost efficiency) with the response text and
   proposal list, asking it to return accepted numbers as a JSON array

All strategies normalize whitespace and are case-insensitive. The parser operates
on the matched proposal set (identified by slug via the workspace proposals.yaml).

Files: langgraph_pipeline/investigation/proposals.py

### D8: File accepted proposals as backlog entries

Addresses: FR7
Satisfies: AC35, AC36, AC37, AC38, AC39

Approach: Implement file_accepted_proposals() in proposals.py that iterates over
accepted proposals and writes markdown files. Defects go to docs/defect-backlog/,
enhancements go to docs/feature-backlog/. Each file follows the standard backlog
format: title, status (Open), priority (mapped from severity), summary (from
proposal description), and description with investigation evidence. File names use
the next available sequence number based on existing backlog items (matching the
pattern {N}-{slugified-title}.md). Filed items are automatically picked up by the
pipeline on the next scan cycle since the supervisor already scans both directories.
The process is fully automated after the Slack approval -- no manual intervention.

Files: langgraph_pipeline/investigation/proposals.py

### D9: Outcome recording in proposals file

Addresses: FR8
Satisfies: AC40, AC41, AC42

Approach: After parsing the user's response, update each Proposal object's status
field to "accepted" or "rejected". For accepted proposals, also set the filed_path
field to the path of the created backlog entry. Update the ProposalSet's overall
status to "approved" (all accepted), "rejected" (none accepted), or "partial"
(some accepted, some rejected). Persist the updated proposals.yaml. This file
serves as the complete audit trail for the investigation, showing all proposals
and the user's disposition of each.

Files: langgraph_pipeline/investigation/proposals.py

### D10: Investigation-specific graph routing

Addresses: FR1
Satisfies: AC7, AC8, AC9

Approach: Modify route_after_intake in edges.py to check for item_type ==
"investigation" and route to run_investigation instead of structure_requirements.
Add two new node name constants: NODE_RUN_INVESTIGATION and
NODE_PROCESS_INVESTIGATION. Add a new routing function
route_after_investigation() that always routes to process_investigation. Add
route_after_process_investigation() that checks should_stop -- if True, return
END (waiting for Slack reply); otherwise return NODE_ARCHIVE. Wire both new
nodes and their conditional edges into graph.py. This gives investigation a
completely separate path from the standard plan-based workflows.

Files: langgraph_pipeline/pipeline/edges.py, langgraph_pipeline/pipeline/graph.py

## Design -> AC Traceability Grid

| AC | Design Decision(s) | Approach |
|---|---|---|
| AC1 | D1 | Investigation submitted through existing pipeline intake mechanism |
| AC2 | D1 | "investigation" added to ItemType literal |
| AC3 | D1 | Supervisor scans investigation backlog, worker processes automatically |
| AC4 | D6 | Slack thread reply polling via conversations.replies API |
| AC5 | D5, D6 | Thread matching via stored thread_ts in proposals.yaml |
| AC6 | D6 | Pipeline waits (should_stop) until Slack reply received before filing |
| AC7 | D1, D10 | Conditional routing in edges.py separates investigation from analysis |
| AC8 | D10 | Investigation produces proposal list, not single document |
| AC9 | D6, D10 | Investigation requires Slack approval before completing |
| AC10 | D2 | Intake runs clause extraction and 5-whys for investigation type |
| AC11 | D3 | Claude reads code, logs, traces referenced in intake output |
| AC12 | D3 | Investigation prompt directs systematic root-cause analysis |
| AC13 | D3 | Proposal descriptions include evidence citations from codebase |
| AC14 | D3, D4 | Proposal model requires type field (defect or enhancement) |
| AC15 | D3, D4 | Proposal model requires title field |
| AC16 | D3, D4 | Proposal model requires description with evidence |
| AC17 | D3, D4 | Proposal model requires severity field |
| AC18 | D3, D4 | Multiple proposals stored in ProposalSet list |
| AC19 | D5 | Proposals formatted as numbered Slack Block Kit message |
| AC20 | D5 | Posted to orchestrator-investigations channel |
| AC21 | D5 | Top-level Slack post enables thread replies |
| AC22 | D4, D5 | thread_ts saved to proposals.yaml after posting |
| AC23 | D5, D6 | Poller matches reply to parent via stored thread_ts |
| AC24 | D4 | Proposals persisted as YAML on disk in workspace |
| AC25 | D4 | Workspace directory keyed by slug provides lookup |
| AC26 | D4 | thread_ts field stored in proposals.yaml |
| AC27 | D4 | File-based persistence survives pipeline restart |
| AC28 | D7 | "all"/"yes" pattern in strategy chain |
| AC29 | D7 | "none"/"no" pattern in strategy chain |
| AC30 | D7 | Comma-separated numbers regex |
| AC31 | D7 | "all except N" regex |
| AC32 | D7 | LLM fallback (Haiku) for free-text |
| AC33 | D7 | Parser operates on matched proposal set from workspace |
| AC34 | D7 | Case-insensitive, whitespace-tolerant matching |
| AC35 | D8 | Defects filed to docs/defect-backlog/ |
| AC36 | D8 | Enhancements filed to docs/feature-backlog/ |
| AC37 | D8 | Uses same markdown format as manually created items |
| AC38 | D8 | Pipeline scans backlog dirs automatically on next cycle |
| AC39 | D8 | No manual intervention beyond Slack approval |
| AC40 | D9 | Proposal status set to "accepted" in proposals.yaml |
| AC41 | D9 | Proposal status set to "rejected" in proposals.yaml |
| AC42 | D9 | proposals.yaml readable after investigation completes |
