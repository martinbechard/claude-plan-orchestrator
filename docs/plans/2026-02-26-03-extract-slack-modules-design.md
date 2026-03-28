# Design: Extract Slack Modules

## Overview

Decompose the monolithic SlackNotifier class into four focused modules under
langgraph_pipeline/slack/. A facade class in __init__.py re-exports from the
submodules to preserve a single import surface.

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
Key types:
- AgentIdentity dataclass (project name, agent name map)
- load_agent_identity(config) factory
- SigningMixin or standalone functions for _sign_text, _as_role

### notifier.py (~400 lines)
Owns: Slack API HTTP calls, channel name caching, message block formatting.

Key API: is_enabled, _post_message, _post_message_get_ts, _build_status_block,
_truncate_for_slack, _get_notifications_channel_id, get_type_channel_id,
send_status, send_defect, send_idea, process_agent_messages, _should_notify.
Constant: MESSAGE_ROUTING_PROMPT (A5 hint).

### poller.py (~400 lines)
Owns: inbound message polling, channel discovery, backlog item creation,
      and four safety layers:

- A1: Chain detection (_is_chain_loop_artifact, _load/_save_intake_history, _record_intake_history)
- A2: Self-reply window tracking (_self_reply_window dict)
- A3: BOT_NOTIFICATION_PATTERN regex filter
- A4: Intake rate limiter (_check_intake_rate_limit, _record_intake_timestamp,
  _load/_save_backlog_throttle, _check_backlog_throttle, _record_backlog_creation)

### suspension.py (~200 lines)
Owns: human-in-the-loop question/answer flows, 5-Whys intake analysis.

Key API: send_question, post_suspension_question, check_suspension_reply,
_check_all_suspensions, answer_question, _answer_question_inner,
_run_intake_analysis, _parse_intake_response.
Type: IntakeState dataclass.

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
