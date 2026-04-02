# Design: 82 Investigation Workflow With Slack Proposals

Source item: tmp/plans/.claimed/82-investigation-workflow-with-slack-proposals.md
Requirements: docs/plans/2026-04-02-82-investigation-workflow-with-slack-proposals-requirements.md
Date: 2026-04-02

## Architecture Overview

The investigation workflow adds a new pipeline workflow type that branches
after intake to run a Claude-powered analysis, produce structured proposals,
post them to Slack for human approval, and file accepted proposals as backlog
items. The design reuses the existing intake stage (clause extraction + 5 Whys)
and the existing Slack thread reply-polling infrastructure from the suspension
module.

### Graph Topology

The existing pipeline graph follows a linear path:

    intake -> structure_requirements -> create_plan -> execute_plan -> verify/archive

Investigation items diverge after intake:

    intake -> run_investigation -> process_investigation -> archive | END

The process_investigation node is a three-phase state machine that uses
should_stop to suspend between pipeline cycles while waiting for a Slack
reply. This mirrors the existing suspension pattern where nodes set
should_stop=True to yield control back to the supervisor.

### Pre-existing Infrastructure (from prior task 1.1)

The following are already implemented and do not need new tasks:
- "investigation" in the ItemType Literal (state.py)
- INVESTIGATION_DIR and COMPLETED_INVESTIGATIONS_DIR paths (paths.py)
- BACKLOG_DIRS and COMPLETED_DIRS entries for investigation (paths.py)
- Investigation scan order in supervisor.py
- route_after_intake branching to NODE_RUN_INVESTIGATION (edges.py)
- route_after_investigation and route_after_process_investigation (edges.py)
- Placeholder run_investigation and process_investigation nodes (investigation.py)
- Graph wiring for both investigation nodes (graph.py)
- Investigation intake handling same as analysis (intake.py)

### Key Files

New files:
- langgraph_pipeline/investigation/__init__.py (package init)
- langgraph_pipeline/investigation/proposals.py (data model, persistence, response parser)
- tests/langgraph/investigation/__init__.py (test package init)
- tests/langgraph/investigation/test_proposals.py (proposal model + parser tests)
- tests/langgraph/pipeline/nodes/test_investigation.py (node function tests)

Modified files:
- langgraph_pipeline/pipeline/nodes/investigation.py (replace placeholders with full implementations)
- langgraph_pipeline/slack/notifier.py (add investigations channel, post_proposals method)
- langgraph_pipeline/slack/poller.py (add investigations to SLACK_CHANNEL_ROLE_SUFFIXES)

---

## Design Decisions

### D1: Proposal data model and persistence

Addresses: FR2 (structured proposal generation), FR4 (proposal state persistence)
Satisfies: AC17, AC18, AC19, AC20, AC25, AC26, AC27, AC28
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

### D2: Flexible response parsing

Addresses: FR5 (response parsing and proposal matching), UC3 (flexible response formats)
Satisfies: AC7, AC8, AC9, AC10, AC11, AC12, AC29, AC30, AC31, AC32
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

Malformed or ambiguous responses that fail all deterministic patterns trigger
the LLM fallback (step 5). If the LLM call also fails to produce valid
output, return an empty set and log a warning (graceful fallback per AC12).
The response is always matched to the correct proposal set via the workspace
slug and thread_ts correlation (AC31).
Files: langgraph_pipeline/investigation/proposals.py

### D3: Investigation analysis engine (run_investigation node)

Addresses: FR1 (investigation workflow type), FR2 (structured proposal generation)
Satisfies: AC3, AC14, AC15, AC16, AC17, AC18, AC19, AC20
Approach: Replace the placeholder run_investigation function in
langgraph_pipeline/pipeline/nodes/investigation.py with a full implementation.
The node is idempotent: first check if proposals.yaml already exists in the
workspace (via load_proposals). If it does, return state unchanged.

If no proposals exist:
1. Read the original item content from item_path
2. Read clause_register_path and five_whys_path from state (intake output)
3. Spawn Claude (Opus model) via langgraph_pipeline/shared/claude_cli.py
   with a structured prompt that:
   - Provides the item content, clause register, and 5-whys as context
   - Instructs Claude to investigate the codebase, reading relevant code,
     logs, data, and traces referenced in the analysis
   - Requires output as a JSON array of proposals, each with: type
     (defect/enhancement), title, description (with evidence citations),
     severity (critical/high/medium/low)
4. Parse the JSON array from Claude's output
5. Construct Proposal objects (numbered 1..N) and a ProposalSet
6. Save to workspace via save_proposals()
7. Return state unchanged (process_investigation handles next steps)

Follow the existing node patterns in intake.py and plan_creation.py for
Claude CLI invocation, output parsing, and error handling. Use the "planner"
permission profile for the Claude call.
Files: langgraph_pipeline/pipeline/nodes/investigation.py

### D4: Slack proposal messaging with threading

Addresses: FR3 (Slack proposal messaging with threading), UC2 (review via Slack)
Satisfies: AC4, AC5, AC6, AC21, AC22, AC23, AC24
Approach: Add "investigations" to SLACK_CHANNEL_ROLE_SUFFIXES in both
notifier.py and poller.py, mapping to "investigation". Add a post_proposals()
method to SlackNotifier that formats proposals as a numbered Block Kit message.
Each proposal shows: number, type badge (defect/enhancement), title, truncated
description, severity. Post as a top-level message to the investigations
channel and return the message ts (thread_ts). The thread_ts is saved to
proposals.yaml so the poller can match replies to their parent proposal.
Files: langgraph_pipeline/slack/notifier.py, langgraph_pipeline/slack/poller.py

### D5: Process investigation state machine (process_investigation node)

Addresses: FR3, FR4, UC2, FR6, FR7
Satisfies: AC4, AC5, AC6, AC21, AC22, AC23, AC24, AC33, AC34, AC35, AC36, AC37, AC38, AC39, AC40, AC41
Approach: Replace the placeholder process_investigation function in
langgraph_pipeline/pipeline/nodes/investigation.py with a three-phase
state machine:

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
to yield control, and the supervisor resumes them on the next cycle. The
complete cycle (post -> poll -> file) runs entirely within Slack interactions,
satisfying the no-context-switch requirement (AC6).
Files: langgraph_pipeline/pipeline/nodes/investigation.py

### D6: Auto-filing accepted proposals as backlog items

Addresses: FR6 (file accepted proposals as backlog items)
Satisfies: AC33, AC34, AC35, AC37
Approach: Add file_accepted_proposals(proposal_set) to proposals.py. For each
accepted proposal: determine target directory (DEFECT_DIR for "defect",
FEATURE_DIR for "enhancement" from paths.py). Find next available sequence
number by scanning existing files. Write markdown using the standard backlog
format: title heading, Status Open, Priority from severity, Summary from
description, Description with investigation evidence. Set proposal.filed_path.
Filed items are automatically picked up by the pipeline because they appear
in the backlog directories that the supervisor scans on each cycle (AC37).
Files: langgraph_pipeline/investigation/proposals.py

### D7: Investigation outcome recording and traceability

Addresses: FR6 (outcome tracking), FR7 (traceability and pipeline re-entry)
Satisfies: AC36, AC38, AC39, AC40, AC41
Approach: After parse_approval_response runs and proposals are filed (D6),
update each Proposal's status field to "accepted" or "rejected". Set
ProposalSet.status to "approved" (all accepted), "rejected" (all rejected),
or "partial" (mixed). Save the final proposals.yaml to the workspace.

The proposals.yaml file serves as a complete audit trail linking the
investigation slug, each proposal's disposition, and the filed_path for
accepted items, establishing full traceability (AC41). Filed backlog items
appear in the standard backlog directories (DEFECT_DIR/FEATURE_DIR) and are
automatically discovered by the supervisor scan on the next cycle (AC38, AC40).
The pipeline processes them identically to manually created items (AC39).
Files: langgraph_pipeline/investigation/proposals.py,
langgraph_pipeline/pipeline/nodes/investigation.py

---

## Design -> AC Traceability Grid

| AC | Design Decision(s) | Approach |
|---|---|---|
| AC1 | Pre-existing | Investigation items submitted via docs/investigation-backlog/, scanned by supervisor |
| AC2 | Pre-existing | ItemType includes "investigation"; route_after_intake branches to run_investigation |
| AC3 | D3 | run_investigation spawns Claude to systematically analyze symptoms and identify root causes |
| AC4 | D4, D5 | post_proposals sends numbered Block Kit message; user reviews in Slack |
| AC5 | D5 | Phase 3 only runs after Slack reply received; no filing without approval |
| AC6 | D4, D5 | Entire flow (post/poll/file) happens in Slack thread; no context-switch needed |
| AC7 | D2 | parse_approval_response: "all"/"yes" returns full set |
| AC8 | D2 | parse_approval_response: "none"/"no" returns empty set |
| AC9 | D2 | parse_approval_response: "1, 3, 5" returns {1, 3, 5} |
| AC10 | D2 | parse_approval_response: "all except 2" returns full set minus {2} |
| AC11 | D2 | parse_approval_response fallback: Claude Haiku interprets free-text |
| AC12 | D2 | Malformed responses trigger LLM fallback; total failure returns empty set with warning |
| AC13 | Pre-existing | route_after_intake returns NODE_RUN_INVESTIGATION for investigation type |
| AC14 | D3 | Claude prompt instructs reading code, logs, data, and traces |
| AC15 | D3 | Output is a JSON array of multiple Proposal objects, not a single document |
| AC16 | D3 | run_investigation reads clause_register_path and five_whys_path from intake output |
| AC17 | D1, D3 | Proposal dataclass has proposal_type constrained to defect/enhancement |
| AC18 | D1, D3 | Proposal dataclass has title field; Claude prompt requires title per proposal |
| AC19 | D1, D3 | Proposal dataclass has description field; Claude prompt requires evidence citations |
| AC20 | D1, D3 | Proposal dataclass has severity field (critical/high/medium/low) |
| AC21 | D4 | post_proposals formats numbered list and sends to orchestrator-investigations channel |
| AC22 | D4 | post_proposals sends as thread-initiating message for reply threading |
| AC23 | D4, D5 | thread_ts from post_proposals saved to proposals.yaml |
| AC24 | D4, D5 | Slack poller matches replies via stored thread_ts |
| AC25 | D1 | proposals.yaml persisted to disk via save_proposals() |
| AC26 | D1 | load_proposals() retrieves by workspace dir; survives process restart |
| AC27 | D1 | Workspace directory keyed by slug; load_proposals(workspace_dir) |
| AC28 | D1 | Implemented as structured YAML file in workspace (tmp/workspace/{slug}/proposals.yaml) |
| AC29 | D2 | Strategy chain steps 1-4 handle structured formats deterministically |
| AC30 | D2 | Strategy chain step 5 falls back to Claude Haiku for free-text |
| AC31 | D2 | Response matched to correct proposal set via workspace slug + thread_ts |
| AC32 | D2 | parse_approval_response returns explicit set of accepted indices |
| AC33 | D6 | Defect proposals filed to docs/defect-backlog/ |
| AC34 | D6 | Enhancement proposals filed to docs/feature-backlog/ |
| AC35 | D6 | Filed items use standard backlog format (title, status, priority, description) |
| AC36 | D7 | proposals.yaml links investigation slug, proposal IDs, statuses, and filed_paths |
| AC37 | D6 | Filed items persisted as durable backlog entries |
| AC38 | D7 | Filed items in DEFECT_DIR/FEATURE_DIR auto-discovered by supervisor scan |
| AC39 | D7 | Filed items use identical format to manually created items; processed the same way |
| AC40 | D7 | No manual step between filing and pipeline pickup |
| AC41 | D7 | proposals.yaml records originating investigation slug + filed_path for each proposal |
