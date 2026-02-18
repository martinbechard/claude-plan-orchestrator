# Design: Configurable Conversation History for Follow-on Question Support

## Overview

Extend `SlackNotifier.answer_question()` to maintain a rolling window of prior Q&A
exchanges and inject that history into each new question's prompt. The window size
is configurable in `slack.local.yaml`, defaulting to 3 turns.

## Problem Statement

Each call to `answer_question()` is currently stateless: the LLM sees only the
current pipeline state and the single question. Follow-on questions lose all prior
context, forcing users to restate background on every message.

## Architecture

### State storage

`SlackNotifier.__init__` gains a new field:

```
self._qa_history: list[tuple[str, str]] = []
```

Each tuple is `(question, answer)`. The list is bounded to `_qa_history_max_turns`
entries, also set from config.

A new constant provides the default window size:

```
QA_HISTORY_DEFAULT_MAX_TURNS = 3
```

### Configuration

`slack.local.yaml` gains an optional `conversation_history` section under `slack`:

```yaml
slack:
  ...
  conversation_history:
    enabled: true        # default: true
    max_turns: 3         # default: 3; set to 0 to disable
```

`SlackNotifier.__init__` reads these values:

```python
conv_config = slack_config.get("conversation_history", {})
self._qa_history_enabled = conv_config.get("enabled", True)
self._qa_history_max_turns = int(conv_config.get("max_turns", QA_HISTORY_DEFAULT_MAX_TURNS))
```

### Prompt injection

`QUESTION_ANSWER_PROMPT` gains a new `{history_context}` placeholder. When history
is empty the placeholder renders as an empty string (no visual noise). When turns
are present they are formatted as:

```
Prior conversation:
Q: <question>
A: <answer>
...

```

The updated prompt template:

```
{history_context}Here is the current pipeline state:
...
Human's question: {question}
Answer:
```

### History management in `answer_question()`

1. Before building the prompt, render history into `history_context`.
2. After receiving the answer, append `(question, answer)` to `self._qa_history`.
3. Trim to `self._qa_history_max_turns` entries (keep the most recent).
4. Skip recording if history is disabled (`self._qa_history_enabled` is False or
   `self._qa_history_max_turns == 0`).

## Key Files

| File | Change |
|------|--------|
| `scripts/plan-orchestrator.py` | Add constant, update `__init__`, update prompt, update `answer_question()` |
| `.claude/slack.local.yaml.template` | Document new `conversation_history` config block |
| `tests/test_slack_notifier.py` | Add tests for history accumulation, trimming, injection, disabling |

## Design Decisions

- **In-memory only.** History is not persisted to disk between process restarts.
  This keeps the implementation simple and avoids cross-session confusion.
- **Thread safety.** `answer_question()` is called from a background thread via
  `threading.Thread`. History reads and writes are short list operations; Python's
  GIL is sufficient for correctness at this scale. No explicit lock is added unless
  concurrent question answering becomes a problem.
- **Default of 3.** Three turns balances context depth against token cost. Each
  additional turn adds ~100–300 tokens of overhead.
- **Disabled when max_turns == 0.** This gives operators a simple numeric knob
  without needing a separate boolean. The `enabled` flag provides an explicit opt-out.
- **Config template update.** The template always documents the new block so new
  users discover the feature immediately.
