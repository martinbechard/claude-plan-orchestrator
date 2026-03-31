# Design: 82 Investigation Workflow With Slack Proposals

Source item: tmp/plans/.claimed/82-investigation-workflow-with-slack-proposals.md
Requirements: docs/plans/2026-03-31-82-investigation-workflow-with-slack-proposals-requirements.md
Date: 2026-03-31

## Architecture Overview

The investigation workflow adds a new pipeline workflow type that branches
after intake to run a Claude-powered analysis, produce structured proposals,
post them to Slack for human approval, and file accepted proposals as backlog
items. The design reuses the existing intake stage (clause extraction + 5 Whys)
and the existing Slack thread reply-polling infrastructure from the suspension
module.

### Graph Topology Extension

The existing pipeline graph follows a linear path:

    intake -> structure_requirements -> create_plan -> execute_plan -> verify/archive

Investigation items diverge after intake:

    intake -> run_investigation -> process_investigation -> archive | END

The process_investigation node is a state machine with three phases that
uses should_stop to suspend between pipeline cycles while waiting for a
Slack reply. This mirrors the existing suspension pattern where nodes set
should_stop=True to yield control back to the supervisor.

### Key Files

New files:
- langgraph_pipeline/investigation/__init__.py (package init)
- langgraph_pipeline/investigation/proposals.py (data model, persistence, response parser)
- langgraph_pipeline/pipeline/nodes/investigation.py (two graph nodes)
- tests/langgraph/investigation/__init__.py (test package init)
- tests/langgraph/investigation/test_proposals.py (proposal model + parser tests)
- tests/langgraph/pipeline/nodes/test_investigation.py (node function tests)

Modified files:
- langgraph_pipeline/pipeline/state.py (add "investigation" to ItemType)
- langgraph_pipeline/shared/paths.py (add investigation dirs)
- langgraph_pipeline/pipeline/edges.py (new node constants, routing functions)
- langgraph_pipeline/pipeline/graph.py (wire investigation nodes)
- langgraph_pipeline/pipeline/nodes/__init__.py (export new nodes)
- langgraph_pipeline/pipeline/nodes/archival.py (handle investigation type)
- langgraph_pipeline/pipeline/nodes/intake.py (handle investigation intake)
- langgraph_pipeline/supervisor.py (include investigation in scan order)
- langgraph_pipeline/slack/notifier.py (add investigations channel, post_proposals method)
- langgraph_pipeline/slack/poller.py (add investigations to SLACK_CHANNEL_ROLE_SUFFIXES)
- tests/langgraph/pipeline/test_edges.py (routing tests for investigation)

---

## Design Decisions

### D1: Investigation type registration

Addresses: UC1 (submit investigation request), FR1 (investigation workflow type)
Satisfies: AC1, AC2, AC3
Approach: Add "investigation" to the ItemType Literal in state.py. Add
INVESTIGATION_DIR = "docs/investigation-backlog" and
COMPLETED_INVESTIGATIONS_DIR = "docs/completed-backlog/investigations" to
paths.py, with entries in BACKLOG_DIRS and COMPLETED_DIRS. Update
supervisor.py to include investigation in the backlog scan order (after
defects and features, before analyses). The pipeline recognizes investigation
items via their directory location, preserving the original request text
in the item file.
Files: langgraph_pipeline/pipeline/state.py, langgraph_pipeline/shared/paths.py,
langgraph_pipeline/supervisor.py

### D2: Investigation intake reuse

Addresses: FR1 (investigation workflow type)
Satisfies: AC6
Approach: In intake.py, handle item_type == "investigation" the same as
"analysis" -- run clause extraction and 5-whys analysis to produce
clause_register_path and five_whys_path. This reuses the existing intake
infrastructure without modification, providing structured context for the
investigation runner.
Files: langgraph_pipeline/pipeline/nodes/intake.py

### D3: Investigation analysis engine (run_investigation node)

Addresses: FR1 (investigation produces multiple proposals), FR2 (structured proposal generation)
Satisfies: AC4, AC5, AC7, AC8, AC9, AC10
Approach: Create run_investigation node function that spawns Claude (Opus
model) via claude_cli.py with a structured prompt. The prompt includes the
original item content, clause register, and 5-whys analysis as context, and
instructs Claude to investigate the codebase and produce a JSON array of
proposals. Each proposal must contain type (defect/enhancement), title,
description with evidence, and severity (critical/high/medium/low). The
node is idempotent: if proposals.yaml already exists in the workspace,
it returns state unchanged. The node follows existing patterns from
intake.py and plan_creation.py for Claude CLI invocation and output parsing.
Uses the "planner" permission profile for the Claude call.
Files: langgraph_pipeline/pipeline/nodes/investigation.py

### D4: Proposal data model and persistence

Addresses: FR4 (proposal state persistence)
Satisfies: AC14, AC16, AC17, AC18, AC19
Approach: Create two dataclasses in langgraph_pipeline/investigation/proposals.py:
- Proposal: number, proposal_type (Literal["defect", "enhancement"]), title,
  description, severity (Literal["critical", "high", "medium", "low"]),
  status (Literal["pending", "accepted", "rejected"]) defaulting to "pending",
  filed_path (Optional[str]) defaulting to None.
- ProposalSet: slug, generated_at (ISO-8601 string), status
  (Literal["pending", "approved", "rejected", "partial"]) defaulting to
  "pending", slack_channel_id (Optional[str]), slack_thread_ts (Optional[str]),
  reply_text (Optional[str]), proposals (list[Proposal]).

Persistence uses workspace YAML files (proposals.yaml in the item workspace
dir). This is the simplest option from the three design alternatives (C14-C16)
and is consistent with how the pipeline already stores per-item artifacts.
save_proposals() writes proposals.yaml via PyYAML safe_dump. load_proposals()
reads and reconstructs the dataclass, returning None if the file is missing.
Lookup is by slug (workspace directory name), and thread_ts is stored
alongside the proposal set.
Files: langgraph_pipeline/investigation/__init__.py,
langgraph_pipeline/investigation/proposals.py

### D5: Slack proposal messaging with threading

Addresses: FR3 (Slack proposal messaging with threading), UC2 (review proposals via Slack)
Satisfies: AC11, AC12, AC13, AC14
Approach: Add "investigations" to SLACK_CHANNEL_ROLE_SUFFIXES in both
notifier.py and poller.py, mapping to "investigation". Add a post_proposals()
method to SlackNotifier that formats proposals as a numbered Block Kit message.
Each proposal shows: number, type badge (defect/enhancement), title, truncated
description, severity. Post as a top-level message to the investigations
channel and return the message ts (thread_ts). The thread_ts is saved to
proposals.yaml so the poller can match replies to their parent proposal.
Files: langgraph_pipeline/slack/notifier.py, langgraph_pipeline/slack/poller.py

### D6: Process investigation state machine (process_investigation node)

Addresses: FR3, FR4, UC2, FR6
Satisfies: AC11, AC12, AC13, AC14, AC15
Approach: The process_investigation node implements a three-phase state machine:

Phase 1 (Post proposals): If proposals.yaml exists but slack_thread_ts is None,
instantiate SlackNotifier, call post_proposals() to send the numbered list,
save the returned thread_ts and channel_id to proposals.yaml, set
should_stop=True, return state.

Phase 2 (Poll for reply): If slack_thread_ts exists but reply_text is None,
call SlackNotifier's check_suspension_reply() to check the thread for a
human reply (skip bot messages). If no reply, set should_stop=True, return
state. If reply found, save reply_text to proposals.yaml, proceed to Phase 3.

Phase 3 (Parse and file): Call parse_approval_response(reply_text,
len(proposals)). For each accepted proposal, call file_accepted_proposals().
Update proposal statuses and save final proposals.yaml. Return state with
should_stop=False so routing proceeds to archive.

This mirrors the existing suspension pattern where nodes set should_stop=True
to yield control, and the supervisor resumes them on the next cycle.
Files: langgraph_pipeline/pipeline/nodes/investigation.py

### D7: Flexible response parsing

Addresses: FR5 (flexible response parsing)
Satisfies: AC20, AC21, AC22, AC23, AC24, AC25
Approach: Create parse_approval_response(text, proposal_count) -> set[int] in
proposals.py. Uses a strategy chain:
1. Strip whitespace, lowercase. "all" or "yes" returns full set.
2. "none" or "no" returns empty set.
3. Regex for comma/space-separated numbers (r"^[\d,\s]+$") parses each
   number, validates in range 1..proposal_count.
4. Regex for "all except" pattern (r"^all\s+except\s+([\d,\s]+)$") computes
   full set minus listed numbers.
5. Fallback: call Claude Haiku via claude_cli.py with a prompt asking it to
   return accepted numbers as a JSON array given the response text and
   proposal count. Parse the JSON array from output.
Files: langgraph_pipeline/investigation/proposals.py

### D8: Auto-filing accepted proposals as backlog items

Addresses: FR6 (auto-filing accepted proposals)
Satisfies: AC26, AC27, AC28, AC29
Approach: Add file_accepted_proposals(proposal_set) to proposals.py. For each
accepted proposal: determine target directory (DEFECT_DIR for "defect",
FEATURE_DIR for "enhancement" from paths.py). Find next available sequence
number by scanning existing files. Write markdown using the standard backlog
format: title heading, Status Open, Priority from severity, Summary from
description, Description with investigation evidence. Set proposal.filed_path.
Filed items are automatically picked up by the pipeline because they appear
in the backlog directories that the supervisor scans on each cycle.
Files: langgraph_pipeline/investigation/proposals.py

### D9: Investigation outcome recording

Addresses: FR7 (investigation outcome recording)
Satisfies: AC30, AC31
Approach: After parse_approval_response runs and proposals are filed (D8),
update each Proposal's status field to "accepted" or "rejected". Set
ProposalSet.status to "approved" (all accepted), "rejected" (all rejected),
or "partial" (mixed). Save the final proposals.yaml to the workspace. A
reviewer can inspect tmp/workspace/{slug}/proposals.yaml to see the
disposition of every proposal.
Files: langgraph_pipeline/investigation/proposals.py,
langgraph_pipeline/pipeline/nodes/investigation.py

### D10: Graph routing for investigation

Addresses: UC1, FR1
Satisfies: AC2
Approach: In edges.py, add NODE_RUN_INVESTIGATION = "run_investigation" and
NODE_PROCESS_INVESTIGATION = "process_investigation" constants. Modify
route_after_intake to check for item_type == "investigation" and return
NODE_RUN_INVESTIGATION instead of NODE_STRUCTURE_REQS. Add
route_after_investigation() returning NODE_PROCESS_INVESTIGATION. Add
route_after_process_investigation() returning END if should_stop is True,
else NODE_ARCHIVE.

In graph.py, import run_investigation and process_investigation from nodes,
add them via add_node(), and wire conditional edges:
run_investigation -> route_after_investigation -> process_investigation,
process_investigation -> route_after_process_investigation -> archive | END.

Update nodes/__init__.py to export both functions. Ensure archival.py handles
the investigation type mapping to the "completed" outcome.
Files: langgraph_pipeline/pipeline/edges.py, langgraph_pipeline/pipeline/graph.py,
langgraph_pipeline/pipeline/nodes/__init__.py,
langgraph_pipeline/pipeline/nodes/archival.py

---

## Design -> AC Traceability Grid

| AC | Design Decision(s) | Approach |
|---|---|---|
| AC1 | D1 | Investigation items submitted via docs/investigation-backlog/, scanned by supervisor |
| AC2 | D1, D10 | ItemType includes "investigation"; route_after_intake branches to run_investigation |
| AC3 | D1 | Original item text preserved in backlog file, accessible to investigation runner |
| AC4 | D3 | run_investigation spawns Claude Opus to read code, logs, traces |
| AC5 | D3 | run_investigation produces a list of Proposal objects, not a single document |
| AC6 | D2 | Intake handles investigation same as analysis (clause extraction + 5 Whys) |
| AC7 | D3, D4 | Proposal dataclass has proposal_type field constrained to defect/enhancement |
| AC8 | D3, D4 | Proposal dataclass has title field |
| AC9 | D3, D4 | Proposal dataclass has description field with evidence citations |
| AC10 | D3, D4 | Proposal dataclass has severity field (critical/high/medium/low) |
| AC11 | D5, D6 | post_proposals sends numbered Block Kit list to Slack investigations channel |
| AC12 | D5 | post_proposals routes to orchestrator-investigations channel |
| AC13 | D5, D6 | Replies captured in same thread via thread_ts correlation |
| AC14 | D4, D5 | thread_ts saved to proposals.yaml alongside proposal data |
| AC15 | D6 | Phase 3 only runs after Slack reply received; no filing without approval |
| AC16 | D4 | proposals.yaml persisted to disk via save_proposals() |
| AC17 | D4 | load_proposals() retrieves by slug (workspace dir); thread_ts enables poller lookup |
| AC18 | D4 | ProposalSet stores all fields: type, title, description, severity, thread_ts |
| AC19 | D4 | File-based persistence survives pipeline restart |
| AC20 | D7 | parse_approval_response: "all"/"yes" returns full set |
| AC21 | D7 | parse_approval_response: "none"/"no" returns empty set |
| AC22 | D7 | parse_approval_response: "1, 3, 5" returns {1, 3, 5} |
| AC23 | D7 | parse_approval_response: "all except 2" returns full set minus {2} |
| AC24 | D7 | parse_approval_response fallback: Claude Haiku interprets free-text |
| AC25 | D7 | Response matched to most recent proposal set via workspace slug lookup |
| AC26 | D8 | Defect proposals filed to docs/defect-backlog/ |
| AC27 | D8 | Enhancement proposals filed to docs/feature-backlog/ |
| AC28 | D8 | Filed items use standard backlog format (title, status, priority, description) |
| AC29 | D8 | Filed items appear in scanned directories, auto-discovered next cycle |
| AC30 | D9 | Each Proposal.status updated to accepted/rejected in proposals.yaml |
| AC31 | D9 | Reviewer inspects tmp/workspace/{slug}/proposals.yaml for full audit trail |
