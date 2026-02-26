# Design: Extract Slack Modules

## Overview

Decompose the monolithic SlackNotifier class (~2,000 lines, plan-orchestrator.py lines 3623-5655)
into four focused modules under langgraph_pipeline/slack/. A facade class in __init__.py
preserves backward compatibility so both scripts can migrate incrementally.

## Architecture

```
langgraph_pipeline/slack/
  __init__.py       # SlackNotifier facade re-exporting from submodules
  identity.py       # AgentIdentity, signing, self-message detection
  notifier.py       # Message posting, channel discovery, formatting
  poller.py         # Inbound polling, dedup, loop prevention layers A1-A4
  suspension.py     # Question posting, reply polling, IntakeState
```

## Module Boundaries

### identity.py (~200 lines)
Extracted from: plan-orchestrator.py top-level (AgentIdentity class at line 1559,
load_agent_identity at line 1586) and SlackNotifier methods set_identity, _as_role,
_sign_text.

Key types:
- AgentIdentity dataclass (project name, agent name map)
- load_agent_identity(config) factory
- SigningMixin or standalone functions for _sign_text, _as_role

### notifier.py (~400 lines)
Extracted from: SlackNotifier __init__, is_enabled, _post_message, _post_message_get_ts,
_build_status_block, _truncate_for_slack, _get_notifications_channel_id,
get_type_channel_id, send_status, send_defect, send_idea, process_agent_messages,
_should_notify, MESSAGE_ROUTING_PROMPT constant (A5 hint).

Owns: Slack API HTTP calls, channel name caching, message block formatting.

### poller.py (~400 lines)
Extracted from: SlackNotifier poll_messages, _discover_channels, _get_channel_role,
_load_last_read_all, _save_last_read_all, start_background_polling, stop_background_polling,
_prune_message_tracking, _handle_polled_messages, _route_message_via_llm,
_execute_routed_action, create_backlog_item, handle_control_command.

Safety layers ported from v1.8.0:
- A1: Chain detection (_is_chain_loop_artifact, _load/_save_intake_history, _record_intake_history)
- A2: Self-reply window tracking (_self_reply_window dict)
- A3: BOT_NOTIFICATION_PATTERN regex filter
- A4: Intake rate limiter (_check_intake_rate_limit, _record_intake_timestamp,
  _load/_save_backlog_throttle, _check_backlog_throttle, _record_backlog_creation)

### suspension.py (~200 lines)
Extracted from: SlackNotifier send_question, post_suspension_question,
check_suspension_reply, _check_all_suspensions, answer_question,
_answer_question_inner, _run_intake_analysis, _run_intake_analysis_inner,
_parse_intake_response. Plus IntakeState dataclass (line 1291).

Owns: human-in-the-loop question/answer flows, 5-Whys intake analysis.

## Migration Strategy

1. Create modules with extracted logic (phases 1-2)
2. Create SlackNotifier facade in __init__.py that delegates to submodule instances
3. Update plan-orchestrator.py imports to use langgraph_pipeline.slack
4. Update auto-pipeline.py imports, removing the importlib.util hack
5. Each module gets its own test file with mocked Slack API calls

## Key Decisions

- Facade pattern: SlackNotifier remains the public API; scripts call the same methods.
  Internally it delegates to the four submodule classes.
- Top-level constants (BOT_NOTIFICATION_PATTERN, MESSAGE_ROUTING_PROMPT, MAX_INTAKES_PER_WINDOW,
  etc.) move into the appropriate submodule as module-level constants.
- IntakeState and AgentIdentity dataclasses move to the submodule that owns them
  (suspension.py and identity.py respectively).
- Socket Mode support (_ensure_socket_mode) stays in notifier.py since it's
  part of the Slack connection lifecycle.

## Dependencies

- Requires langgraph_pipeline package structure from 01-langgraph-project-scaffold (completed)
- The slack/__init__.py stub already exists (empty)
