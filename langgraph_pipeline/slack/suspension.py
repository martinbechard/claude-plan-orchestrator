# langgraph_pipeline/slack/suspension.py
# Human-in-the-loop question/answer flows, 5-Whys intake analysis, IntakeState.
# Design: docs/plans/2026-02-26-03-extract-slack-modules-design.md

"""IntakeState dataclass, SuspensionCallbacks, and SlackSuspension class.

Extracted from plan-orchestrator.py SlackNotifier class (~line 3977).
Covers send_question, post_suspension_question, check_suspension_reply,
_check_all_suspensions, answer_question, _answer_question_inner,
_run_intake_analysis, _run_intake_analysis_inner, _parse_intake_response.
IntakeState dataclass (plan-orchestrator.py line 1291).
"""

import contextlib
import glob as glob_module
import json
import os
import re
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from langgraph_pipeline.slack.identity import AGENT_ROLE_INTAKE, AGENT_ROLE_QA

# ── Constants ─────────────────────────────────────────────────────────────────

SLACK_QUESTION_PATH = ".claude/slack-pending-question.json"
SLACK_ANSWER_PATH = ".claude/slack-answer.json"
SLACK_POLL_INTERVAL_SECONDS = 15
SLACK_THREAD_REPLIES_LIMIT = 5
SUSPENDED_DIR = ".claude/suspended"
SLACK_LLM_MODEL = "claude-opus-4-6"
QA_HISTORY_DEFAULT_MAX_TURNS = 3
REQUIRED_FIVE_WHYS_COUNT = 5
INTAKE_CLARITY_THRESHOLD = 3
INTAKE_ANALYSIS_TIMEOUT_SECONDS = 120  # 2 minutes for intake LLM call
RAG_TOP_K = 5
RAG_SIMILARITY_THRESHOLD = 0.75

INTAKE_CLARIFICATION_TEMPLATE = (
    ":thinking_face: *I need a bit more context to create a useful backlog item.*\n"
    "\n"
    "Could you provide more detail? For example:\n"
    "- What exactly happened, and what did you expect instead?\n"
    "- Which part of the system is affected?\n"
    "- Steps to reproduce (if it's a defect)?\n"
    "\n"
    "_Please reply with more context and I'll create the backlog item._"
)

INTAKE_ACK_TEMPLATE = (
    "*Here is my understanding of your {item_type}:*\n"
    "\n"
    "*Title:* {title}\n"
    "*Classification:* {classification}\n"
    "*Root need:* {root_need}\n"
    "\n"
    "_Creating backlog item..._"
)

QUESTION_ANSWER_PROMPT = """You are an AI pipeline orchestrator answering a human's question via Slack.

{history_context}Here is the current pipeline state:

{state_context}

Important context:
- The human runs you via Claude Code on a Max subscription, NOT the direct API.
- The "total_cost_usd" in session logs is an API-equivalent estimate reported by
  Claude CLI. It does NOT represent actual charges for subscription users. If asked
  about costs, explain this clearly.
- Keep your answer concise (2-6 lines) and conversational. Use Slack mrkdwn formatting
  (*bold*, _italic_) sparingly.
- Only include information relevant to the question. Do not dump all available data.
- If you genuinely cannot answer from the available state, say so honestly.

Human's question: {question}

Answer:"""

INTAKE_ANALYSIS_PROMPT = """Analyze this {item_type} request using the 5 Whys method.

Request: {text}

Perform a 5 Whys analysis to uncover the root need behind this request.
IMPORTANT: You MUST provide exactly 5 numbered "Why" questions and answers. Do not stop at fewer than 5. Each Why should dig deeper into the root cause of the previous answer.
Then write a concise backlog item with a clear title and description.
Also classify whether this is truly a {item_type} or should be categorized differently.

Also rate the clarity of the original request on a 1-5 scale:
1 = completely vague (e.g. "try again", "fix it")
2 = very little context, hard to act on
3 = some context but missing key details
4 = clear enough to investigate
5 = fully detailed with steps, context, and expected outcome

Format your response exactly like this:

Title: <one-line title for the backlog item>

Classification: <defect|feature|question> - <one sentence explaining why>

Clarity: <1-5 integer rating>

5 Whys:
1. <why>
2. <why>
3. <why>
4. <why>
5. <why>

Root Need: <the root need uncovered by the analysis>

Description:
<2-4 sentence description of the backlog item, incorporating the root need>
Keep it concise and actionable."""

INTAKE_RETRY_PROMPT = """Your previous 5 Whys analysis was incomplete - you only provided {count} out of 5 required Whys.

Original {item_type} request: {text}

Your previous analysis:
{analysis}

Please redo the analysis with EXACTLY 5 numbered Whys. Each Why must dig deeper into the previous answer to uncover the true root cause.

Format your response exactly like this:

Title: <one-line title for the backlog item>

Classification: <defect|feature|question> - <one sentence explaining why>

5 Whys:
1. <why>
2. <why>
3. <why>
4. <why>
5. <why>

Root Need: <the root need uncovered by the analysis>

Description:
<2-4 sentence description of the backlog item, incorporating the root need>
Keep it concise and actionable."""


# ── IntakeState ───────────────────────────────────────────────────────────────


@dataclass
class IntakeState:
    """Tracks the state of an async 5 Whys intake analysis.

    Each inbound feature/defect request gets one IntakeState that lives
    for the duration of the analysis thread.
    """

    channel_id: str
    channel_name: str
    original_text: str
    user: str
    ts: str
    item_type: str  # "feature" or "defect"
    status: str = field(default="analyzing")  # "analyzing", "creating", "done", "failed"
    analysis: str = field(default="")  # LLM 5-Whys output


# ── SuspensionCallbacks ───────────────────────────────────────────────────────


@dataclass
class SuspensionCallbacks:
    """Cross-module callbacks injected into SlackSuspension.

    All fields are optional. Missing callbacks result in no-ops so the class
    can be tested incrementally without a full SlackNotifier or SlackPoller.

    Attributes:
        post_message: Slack HTTP post — (payload, channel_id) -> bool.
        post_message_ts: Post returning ts — (payload, channel_id) -> Optional[str].
        build_block: Block Kit formatter — (message, level) -> dict.
        truncate: Text truncator — (text, max_length) -> str.
        send_status: Status notifier — (message, level, channel_id) -> None.
        get_type_channel: Channel lookup — (item_type) -> str.
        sign_text: Message signing — (text) -> str.
        as_role: Role context manager factory — (role) -> ContextManager.
        ensure_socket_mode: Socket Mode check — () -> bool.
        should_notify: Notify event check — (event) -> bool.
        call_claude: LLM invocation — (prompt, model, timeout) -> ClaudeResult.
        probe_quota: Quota availability probe — () -> bool. If None, quota is assumed available.
        gather_state: Pipeline state — () -> dict.
        format_state: State formatter — (state) -> str.
        create_backlog: Backlog creation — (item_type, title, body, user, ts) -> Optional[dict].
        check_intake_rate: Rate limit check — () -> bool.
        record_intake: Rate limit recording — () -> None.
        intake_lock: Shared lock protecting pending_intakes.
        pending_intakes: Shared dict of active IntakeState keyed by channel:ts.
        rag: RAG instance for deduplication (duck-typed).
    """

    post_message: Optional[Callable] = None
    post_message_ts: Optional[Callable] = None
    build_block: Optional[Callable] = None
    truncate: Optional[Callable] = None
    send_status: Optional[Callable] = None
    get_type_channel: Optional[Callable] = None
    sign_text: Optional[Callable] = None
    as_role: Optional[Callable] = None
    ensure_socket_mode: Optional[Callable] = None
    should_notify: Optional[Callable] = None
    call_claude: Optional[Callable] = None
    probe_quota: Optional[Callable] = None
    gather_state: Optional[Callable] = None
    format_state: Optional[Callable] = None
    create_backlog: Optional[Callable] = None
    check_intake_rate: Optional[Callable] = None
    record_intake: Optional[Callable] = None
    intake_lock: Optional[threading.Lock] = None
    pending_intakes: Optional[dict] = None
    rag: Optional[object] = None


# ── SlackSuspension ───────────────────────────────────────────────────────────


class SlackSuspension:
    """Human-in-the-loop question/answer flows and 5-Whys intake analysis.

    Owns: question/answer wait loops, suspension reply polling, and
    5-Whys intake analysis with optional RAG deduplication.

    Cross-module operations (HTTP posting, LLM calls, backlog creation)
    are injected via SuspensionCallbacks for independent testability.
    """

    def __init__(
        self,
        bot_token: str,
        question_config: dict,
        callbacks: Optional[SuspensionCallbacks] = None,
        qa_history_enabled: bool = True,
        qa_history_max_turns: int = QA_HISTORY_DEFAULT_MAX_TURNS,
    ) -> None:
        """Initialize SlackSuspension with Slack credentials and callbacks.

        Args:
            bot_token: Slack bot token for conversations.replies API calls.
            question_config: Dict from slack.local.yaml 'questions' section.
            callbacks: Cross-module callbacks. Defaults to no-op SuspensionCallbacks.
            qa_history_enabled: Whether to maintain a rolling Q&A history window.
            qa_history_max_turns: Maximum Q&A history turns to retain per session.
        """
        self._bot_token = bot_token
        self._question_config = question_config
        self._callbacks = callbacks or SuspensionCallbacks()
        self._qa_history_enabled = qa_history_enabled
        self._qa_history_max_turns = qa_history_max_turns
        self._qa_history: list[tuple[str, str]] = []
        self._pending_answer: Optional[threading.Event] = None
        self._last_answer: Optional[str] = None

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _sign_text(self, text: str) -> str:
        """Sign text via callbacks.sign_text, or return unchanged if not set."""
        if self._callbacks.sign_text:
            return self._callbacks.sign_text(text)
        return text

    def _truncate(self, text: str, max_length: int = 2900) -> str:
        """Truncate text via callbacks.truncate, or return unchanged if not set."""
        if self._callbacks.truncate:
            return self._callbacks.truncate(text, max_length)
        return text

    @contextlib.contextmanager
    def _as_role(self, role: str):
        """Switch to a role context via callbacks.as_role, or use a no-op context."""
        if self._callbacks.as_role:
            with self._callbacks.as_role(role):
                yield
        else:
            yield

    def receive_answer(self, value: str) -> None:
        """Record a Socket Mode button-click answer and unblock the waiting thread.

        Called by the Socket Mode button-click handler registered in notifier.py.
        The facade (task 3.1) wires this method as the on_answer callback.

        Args:
            value: The answer value from the Slack block action payload.
        """
        self._last_answer = value
        if self._pending_answer:
            self._pending_answer.set()

    # ── Suspension reply polling ──────────────────────────────────────────────

    def check_suspension_reply(
        self,
        channel_id: str,
        thread_ts: str,
    ) -> Optional[str]:
        """Check for a human reply in a Slack thread.

        Uses conversations.replies API to check if there are replies to the
        suspension question message. Ignores the original message and bot messages.

        Args:
            channel_id: Slack channel ID containing the thread.
            thread_ts: Timestamp of the original question message (thread root).

        Returns:
            Text of the first human reply if found, None otherwise.
        """
        if not self._bot_token or not channel_id or not thread_ts:
            return None

        try:
            params = urllib.parse.urlencode({
                "channel": channel_id,
                "ts": thread_ts,
                "limit": SLACK_THREAD_REPLIES_LIMIT,
            })
            req = urllib.request.Request(
                f"https://slack.com/api/conversations.replies?{params}",
                headers={"Authorization": f"Bearer {self._bot_token}"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read())

            if not result.get("ok", False):
                print(f"[SLACK] conversations.replies error: {result.get('error', 'unknown')}")
                return None

            for message in result.get("messages", []):
                if message.get("ts") == thread_ts:
                    continue  # Skip the root message
                if "bot_id" in message:
                    continue  # Skip bot messages
                return message.get("text")

            return None

        except Exception as e:
            print(f"[SLACK] Failed to check thread replies: {e}")
            return None

    def _check_all_suspensions(self) -> None:
        """Check all suspended items for Slack thread replies.

        Called periodically by the background poller. For each suspension
        marker with a slack_thread_ts, checks for human replies. If a reply is
        found, writes it back to the marker file and sends a confirmation message.
        """
        pattern = os.path.join(SUSPENDED_DIR, "*.json")
        for marker_path in glob_module.glob(pattern):
            try:
                with open(marker_path, "r", encoding="utf-8") as f:
                    marker = json.load(f)

                thread_ts = marker.get("slack_thread_ts")
                channel_id = marker.get("slack_channel_id")
                if not thread_ts or not channel_id:
                    continue

                if "answer" in marker:
                    continue

                reply = self.check_suspension_reply(channel_id, thread_ts)
                if reply is None:
                    continue

                slug = marker.get("slug", os.path.basename(marker_path))
                marker["answer"] = reply
                with open(marker_path, "w", encoding="utf-8") as f:
                    json.dump(marker, f, indent=2)

                confirmation = self._sign_text(
                    f":white_check_mark: Answer received for {slug}. "
                    "Item will resume on next pipeline cycle."
                )
                if self._callbacks.post_message:
                    self._callbacks.post_message({"text": confirmation}, channel_id)
                print(f"[SLACK] Answer received for suspended item: {slug}")

            except Exception as e:
                print(f"[SLACK] Error checking suspension {marker_path}: {e}")

    def post_suspension_question(
        self,
        slug: str,
        item_type: str,
        question: str,
        question_context: str,
    ) -> Optional[str]:
        """Post a suspension question to the type-specific Slack channel.

        Args:
            slug: Work item slug (e.g., "9-ux-feature").
            item_type: "feature" or "defect".
            question: The question text.
            question_context: Why this information is needed.

        Returns:
            Message ts (thread_ts) for reply correlation, None on failure.
        """
        channel_id = (
            self._callbacks.get_type_channel(item_type)
            if self._callbacks.get_type_channel
            else ""
        )
        if not channel_id:
            print(f"[SLACK] No channel found for item_type={item_type}")
            return None

        payload = {
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f":question: Design Question for {slug}",
                    },
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": self._truncate(f"*Question:* {question}"),
                    },
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": self._truncate(f"*Context:* {question_context}"),
                    },
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": self._sign_text(
                                "_Reply in this thread to answer. "
                                "The pipeline will resume processing automatically._"
                            ),
                        }
                    ],
                },
            ]
        }

        if self._callbacks.post_message_ts:
            return self._callbacks.post_message_ts(payload, channel_id)
        return None

    # ── Interactive question flow ─────────────────────────────────────────────

    def send_question(
        self,
        question: str,
        options: list[str],
        timeout_minutes: int = 0,
    ) -> Optional[str]:
        """Send a question to Slack and wait for a human answer.

        Uses Socket Mode for interactive buttons if available, otherwise falls
        back to file-based polling via SLACK_ANSWER_PATH.

        Args:
            question: Question text to display.
            options: List of valid answer options.
            timeout_minutes: Timeout in minutes (0 = use config default).

        Returns:
            Answer string if received, configured fallback value on timeout, None on error.
        """
        if self._callbacks.should_notify and not self._callbacks.should_notify("on_question"):
            return None
        if not self._question_config.get("enabled", False):
            return None

        effective_timeout = timeout_minutes or self._question_config.get("timeout_minutes", 60)
        fallback = self._question_config.get("fallback", "skip")

        use_socket = (
            self._callbacks.ensure_socket_mode()
            if self._callbacks.ensure_socket_mode
            else False
        )

        if use_socket:
            payload = self._build_socket_question_payload(question, options)
        else:
            options_text = " | ".join(f"`{opt}`" for opt in options)
            msg = (
                f":question: *{question}*\nOptions: {options_text}\n"
                '_Reply by creating `.claude/slack-answer.json` with `{"answer": "your_choice"}`_'
            )
            payload = (
                self._callbacks.build_block(msg, "question")
                if self._callbacks.build_block
                else {"text": msg}
            )

        if self._callbacks.post_message:
            self._callbacks.post_message(payload, None)

        if use_socket:
            return self._wait_socket_answer(effective_timeout, fallback)
        return self._poll_file_answer(effective_timeout, fallback, question, options)

    def _build_socket_question_payload(self, question: str, options: list[str]) -> dict:
        """Build a Block Kit payload with action buttons for Socket Mode.

        Args:
            question: Question text.
            options: Answer options shown as interactive buttons.
        """
        actions = [
            {
                "type": "button",
                "text": {"type": "plain_text", "text": opt},
                "action_id": f"orchestrator_answer_{i}",
                "value": opt,
            }
            for i, opt in enumerate(options)
        ]
        return {
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": self._sign_text(f":question: *{question}*"),
                    },
                },
                {"type": "actions", "elements": actions},
            ]
        }

    def _wait_socket_answer(self, timeout_minutes: int, fallback: str) -> str:
        """Wait for a Socket Mode button-click answer via threading.Event.

        Args:
            timeout_minutes: How long to wait before returning fallback.
            fallback: Value to return if no answer is received in time.
        """
        self._pending_answer = threading.Event()
        self._last_answer = None
        answered = self._pending_answer.wait(timeout=timeout_minutes * 60)
        if answered and self._last_answer:
            return self._last_answer
        return fallback

    def _poll_file_answer(
        self,
        timeout_minutes: int,
        fallback: str,
        question: str,
        options: list[str],
    ) -> Optional[str]:
        """Poll SLACK_ANSWER_PATH for a file-based answer.

        Writes pending question state to SLACK_QUESTION_PATH and polls
        SLACK_ANSWER_PATH until answered or timed out.

        Args:
            timeout_minutes: How long to poll before returning fallback.
            fallback: Value to return on timeout.
            question: Question text (written to pending question file).
            options: Valid answer options.
        """
        question_data = {
            "question": question,
            "options": options,
            "asked_at": datetime.now(ZoneInfo("UTC")).isoformat(),
            "timeout_minutes": timeout_minutes,
        }
        try:
            with open(SLACK_QUESTION_PATH, "w") as f:
                json.dump(question_data, f, indent=2)
        except IOError as e:
            print(f"[SLACK] Failed to write question file: {e}")
            return None

        start_time = time.time()
        timeout_seconds = timeout_minutes * 60

        while time.time() - start_time < timeout_seconds:
            try:
                if os.path.exists(SLACK_ANSWER_PATH):
                    with open(SLACK_ANSWER_PATH, "r") as f:
                        answer_data = json.load(f)
                    answer = answer_data.get("answer", "")
                    for path in (SLACK_ANSWER_PATH, SLACK_QUESTION_PATH):
                        try:
                            os.remove(path)
                        except OSError:
                            pass
                    return answer
            except (IOError, json.JSONDecodeError) as e:
                print(f"[SLACK] Error reading answer file: {e}")

            time.sleep(SLACK_POLL_INTERVAL_SECONDS)

        try:
            os.remove(SLACK_QUESTION_PATH)
        except OSError:
            pass
        return fallback

    # ── Q&A with pipeline context ─────────────────────────────────────────────

    def answer_question(self, question: str, channel_id: Optional[str] = None) -> None:
        """Respond to a question from Slack using an LLM call with pipeline context.

        Maintains a rolling window of prior Q&A exchanges injected into each prompt.

        Args:
            question: The question text.
            channel_id: Reply to this channel. Falls back to notifier default.
        """
        with self._as_role(AGENT_ROLE_QA):
            self._answer_question_inner(question, channel_id)

    def _answer_question_inner(self, question: str, channel_id: Optional[str] = None) -> None:
        """Inner implementation of answer_question, executed under QA role."""
        print(f"[SLACK] Answering question: {question[:80]}")

        history_context = ""
        if self._qa_history_enabled and self._qa_history_max_turns > 0 and self._qa_history:
            lines = ["Prior conversation:"]
            for prior_q, prior_a in self._qa_history:
                lines.append(f"Q: {prior_q}")
                lines.append(f"A: {prior_a}")
            lines.append("")
            history_context = "\n".join(lines) + "\n"

        state = self._callbacks.gather_state() if self._callbacks.gather_state else {}
        state_context = (
            self._callbacks.format_state(state)
            if self._callbacks.format_state
            else str(state)
        )
        prompt = QUESTION_ANSWER_PROMPT.format(
            history_context=history_context,
            state_context=state_context,
            question=question,
        )

        try:
            answer = (
                self._callbacks.call_claude(prompt, SLACK_LLM_MODEL, None).text
                if self._callbacks.call_claude
                else ""
            )
            if not answer:
                answer = f"_(LLM returned empty)_\n{state_context}"
        except Exception as e:
            print(f"[SLACK] LLM answer failed: {e}")
            answer = f"_(LLM unavailable)_\n{state_context}"

        print(f"[SLACK] Answer: {answer[:120]}")
        if self._callbacks.send_status:
            self._callbacks.send_status(answer, "info", channel_id)

        if self._qa_history_enabled and self._qa_history_max_turns > 0:
            self._qa_history.append((question, answer))
            if len(self._qa_history) > self._qa_history_max_turns:
                self._qa_history = self._qa_history[-self._qa_history_max_turns:]

    # ── Intake analysis ───────────────────────────────────────────────────────

    @staticmethod
    def _parse_intake_response(text: str) -> dict:
        """Parse a plain-text intake analysis response into structured fields.

        Extracts Title, Classification, Clarity, Root Need, Description, and
        5 Whys numbered list from the LLM response. Falls back gracefully on
        unexpected format.

        Args:
            text: Raw LLM response text.

        Returns:
            Dict with keys: title, root_need, description, five_whys (list),
            classification, clarity (int, 0 if absent).
        """
        result: dict = {
            "title": "",
            "root_need": "",
            "description": "",
            "five_whys": [],
            "classification": "",
            "clarity": 0,
        }

        title_match = re.search(r"^Title:\s*(.+)$", text, re.MULTILINE)
        if title_match:
            result["title"] = title_match.group(1).strip()

        class_match = re.search(r"^Classification:\s*(.+)$", text, re.MULTILINE)
        if class_match:
            result["classification"] = class_match.group(1).strip()

        clarity_match = re.search(r"^Clarity:\s*(\d+)", text, re.MULTILINE)
        if clarity_match:
            result["clarity"] = int(clarity_match.group(1))

        root_match = re.search(r"^Root Need:\s*(.+)$", text, re.MULTILINE)
        if root_match:
            result["root_need"] = root_match.group(1).strip()

        desc_match = re.search(r"^Description:\s*\n(.*)", text, re.MULTILINE | re.DOTALL)
        if desc_match:
            result["description"] = desc_match.group(1).strip()

        whys_match = re.search(r"5 Whys:\s*\n((?:\d+\..+\n?)+)", text)
        if whys_match:
            whys_text = whys_match.group(1)
            result["five_whys"] = [
                m.group(1).strip() for m in re.finditer(r"\d+\.\s*(.+)", whys_text)
            ]

        return result

    def _run_intake_analysis(self, intake: IntakeState) -> None:
        """Run 5-Whys intake analysis in a background thread.

        Calls Claude CLI via callbacks.call_claude to analyze the request,
        then creates the backlog item and sends Slack confirmation.

        Args:
            intake: The IntakeState tracking this analysis.
        """
        with self._as_role(AGENT_ROLE_INTAKE):
            self._run_intake_analysis_inner(intake)

    def _run_intake_analysis_inner(self, intake: IntakeState) -> None:
        """Inner implementation of _run_intake_analysis, executed under Intake role."""
        intake_key = f"{intake.channel_name}:{intake.ts}"
        fallback_title = intake.original_text.split("\n", 1)[0][:80]

        if self._callbacks.check_intake_rate and self._callbacks.check_intake_rate():
            intake.status = "done"
            return

        if self._callbacks.record_intake:
            self._callbacks.record_intake()

        try:
            if self._callbacks.send_status:
                self._callbacks.send_status(
                    f"*Received your {intake.item_type} request.* Analyzing...",
                    "info",
                    intake.channel_id,
                )
        except Exception:
            pass  # Best-effort acknowledgment, do not block analysis

        try:
            # Gate intake on quota availability before spawning a doomed subprocess.
            if self._callbacks.probe_quota and not self._callbacks.probe_quota():
                failure_reason = "quota exhausted — analysis skipped"
                print(f"[INTAKE] Quota unavailable: {failure_reason}")
                try:
                    from langgraph_pipeline.web.dashboard_state import get_dashboard_state
                    get_dashboard_state().add_error(
                        f"[INTAKE] call_claude skipped: {failure_reason}"
                    )
                except Exception:
                    pass
                item_info = self._create_backlog_item(
                    intake.item_type, fallback_title,
                    intake.original_text, intake.user, intake.ts,
                )
                item_ref = _format_item_ref(item_info)
                if self._callbacks.send_status:
                    self._callbacks.send_status(
                        f"*{intake.item_type.title()} received{item_ref}:* {fallback_title}\n"
                        f"_(Analysis unavailable: {failure_reason} — created from raw text)_",
                        "success",
                        intake.channel_id,
                    )
                intake.status = "done"
                return

            prompt = INTAKE_ANALYSIS_PROMPT.format(
                item_type=intake.item_type, text=intake.original_text
            )
            result = (
                self._callbacks.call_claude(
                    prompt, SLACK_LLM_MODEL, INTAKE_ANALYSIS_TIMEOUT_SECONDS
                )
                if self._callbacks.call_claude
                else None
            )
            response_text = result.text if result else ""

            if not response_text:
                failure_reason = (result.failure_reason if result else None) or "LLM returned empty response"
                print(f"[INTAKE] LLM call failed: {failure_reason}")
                try:
                    from langgraph_pipeline.web.dashboard_state import get_dashboard_state
                    get_dashboard_state().add_error(
                        f"[INTAKE] call_claude failed: {failure_reason}"
                    )
                except Exception:
                    pass
                item_info = self._create_backlog_item(
                    intake.item_type, fallback_title,
                    intake.original_text, intake.user, intake.ts,
                )
                item_ref = _format_item_ref(item_info)
                if self._callbacks.send_status:
                    self._callbacks.send_status(
                        f"*{intake.item_type.title()} received{item_ref}:* {fallback_title}\n"
                        f"_(Analysis unavailable: {failure_reason} — created from raw text)_",
                        "success",
                        intake.channel_id,
                    )
                intake.status = "done"
                return

            parsed = self._parse_intake_response(response_text)
            intake.analysis = response_text
            title = parsed["title"] or fallback_title
            root_need = parsed["root_need"]
            five_whys = parsed["five_whys"]
            classification = parsed["classification"]

            if len(five_whys) < REQUIRED_FIVE_WHYS_COUNT:
                title, root_need, five_whys, classification, response_text, parsed = (
                    self._retry_five_whys(
                        intake, response_text, title, root_need,
                        five_whys, classification, fallback_title,
                    )
                )
                intake.analysis = response_text

            if len(five_whys) < REQUIRED_FIVE_WHYS_COUNT:
                print(
                    f"[INTAKE] WARNING: Only {len(five_whys)}/{REQUIRED_FIVE_WHYS_COUNT} "
                    "Whys in final analysis"
                )

            clarity = parsed.get("clarity", 0)
            if clarity > 0 and clarity < INTAKE_CLARITY_THRESHOLD:
                self._send_clarification_request(intake)
                intake.status = "done"
                return

            self._send_intake_ack(intake, title, classification, root_need)

            description = self._build_description(parsed, response_text, five_whys, root_need)

            rag = self._callbacks.rag
            rag_collection = "defects" if intake.item_type == "defect" else "features"
            if rag and getattr(rag, "available", False):
                similar = rag.query_similar(
                    f"{title}\n{description[:500]}", rag_collection, top_k=RAG_TOP_K
                )
                high_sim = [s for s in similar if s["similarity"] >= RAG_SIMILARITY_THRESHOLD]
                if high_sim:
                    if self._run_dedup_check(intake, title, description, high_sim, rag):
                        intake.status = "done"
                        return

            intake.status = "creating"
            item_info = self._create_backlog_item(
                intake.item_type, title, description, intake.user, intake.ts,
            )
            if item_info and rag and getattr(rag, "available", False):
                rag.add_item(rag_collection, item_info["filepath"], title, description)

            item_ref = _format_item_ref(item_info)
            notify_msg = f"*{intake.item_type.title()} created{item_ref}:* {title}"
            if classification:
                notify_msg += f"\n_Classification: {classification}_"
            if root_need:
                notify_msg += f"\n_Root need: {root_need}_"
            if self._callbacks.send_status:
                self._callbacks.send_status(notify_msg, "success", intake.channel_id)
            intake.status = "done"

        except Exception as e:
            print(f"[INTAKE] Error in intake analysis: {e}")
            intake.status = "failed"
            try:
                item_info = self._create_backlog_item(
                    intake.item_type, fallback_title,
                    intake.original_text, intake.user, intake.ts,
                )
                item_ref = _format_item_ref(item_info)
                if self._callbacks.send_status:
                    self._callbacks.send_status(
                        f"*{intake.item_type.title()} received{item_ref}:* {fallback_title}\n"
                        f"_(Error during analysis: {e})_",
                        "warning",
                        intake.channel_id,
                    )
            except Exception:
                pass
        finally:
            lock = self._callbacks.intake_lock
            pending = self._callbacks.pending_intakes
            if lock is not None and pending is not None:
                with lock:
                    pending.pop(intake_key, None)

    def _retry_five_whys(
        self,
        intake: IntakeState,
        response_text: str,
        title: str,
        root_need: str,
        five_whys: list[str],
        classification: str,
        fallback_title: str,
    ) -> tuple:
        """Retry 5 Whys analysis if initial response had fewer than required Whys.

        Returns an updated tuple of (title, root_need, five_whys, classification,
        response_text, parsed) using retry results if they are better.

        Args:
            intake: Current intake state.
            response_text: Initial LLM response.
            title: Parsed title from initial response.
            root_need: Parsed root need from initial response.
            five_whys: Parsed Whys list from initial response.
            classification: Parsed classification from initial response.
            fallback_title: Raw first line of original text as backup title.
        """
        print(f"[INTAKE] Only {len(five_whys)} Whys returned, retrying...")
        retry_prompt = INTAKE_RETRY_PROMPT.format(
            count=len(five_whys),
            item_type=intake.item_type,
            text=intake.original_text,
            analysis=response_text,
        )
        retry_text = (
            self._callbacks.call_claude(
                retry_prompt, SLACK_LLM_MODEL, INTAKE_ANALYSIS_TIMEOUT_SECONDS
            ).text
            if self._callbacks.call_claude
            else ""
        )
        if retry_text:
            retry_parsed = self._parse_intake_response(retry_text)
            if len(retry_parsed["five_whys"]) >= len(five_whys):
                parsed = retry_parsed
                response_text = retry_text
                title = parsed["title"] or fallback_title
                root_need = parsed["root_need"]
                five_whys = parsed["five_whys"]
                classification = parsed["classification"]
                return title, root_need, five_whys, classification, response_text, parsed

        return title, root_need, five_whys, classification, response_text, \
            self._parse_intake_response(response_text)

    def _send_clarification_request(self, intake: IntakeState) -> None:
        """Send a clarification request when the clarity score is below threshold.

        Args:
            intake: Current intake state for channel and thread context.
        """
        print(
            f"[INTAKE] Low clarity score for {intake.item_type} — requesting clarification"
        )
        try:
            if self._callbacks.build_block and self._callbacks.post_message:
                payload = self._callbacks.build_block(INTAKE_CLARIFICATION_TEMPLATE, "warning")
                if intake.ts:
                    payload["thread_ts"] = intake.ts
                self._callbacks.post_message(payload, intake.channel_id)
        except Exception as exc:
            print(f"[INTAKE] Failed to send clarification reply: {exc}")

    def _send_intake_ack(
        self,
        intake: IntakeState,
        title: str,
        classification: str,
        root_need: str,
    ) -> None:
        """Send analysis summary acknowledgment before creating the backlog item.

        Args:
            intake: Current intake state.
            title: Parsed item title.
            classification: Parsed classification.
            root_need: Parsed root need.
        """
        try:
            if self._callbacks.send_status:
                ack_msg = INTAKE_ACK_TEMPLATE.format(
                    item_type=intake.item_type,
                    title=title,
                    classification=classification or "unknown",
                    root_need=root_need or "not identified",
                )
                self._callbacks.send_status(ack_msg, "info", intake.channel_id)
        except Exception:
            pass  # Best-effort, do not block backlog creation

    def _build_description(
        self,
        parsed: dict,
        response_text: str,
        five_whys: list[str],
        root_need: str,
    ) -> str:
        """Build the backlog item description by enriching parsed text with Whys.

        Args:
            parsed: Parsed LLM response dict.
            response_text: Full raw LLM response as fallback.
            five_whys: List of Why strings.
            root_need: Root need text.
        """
        description = parsed["description"] or response_text
        if five_whys:
            whys_text = "\n".join(f"  {i + 1}. {w}" for i, w in enumerate(five_whys))
            description += f"\n\n## 5 Whys Analysis\n\n{whys_text}"
        if root_need:
            description += f"\n\n**Root Need:** {root_need}"
        return description

    def _create_backlog_item(
        self,
        item_type: str,
        title: str,
        body: str,
        user: str,
        ts: str,
    ) -> Optional[dict]:
        """Invoke callbacks.create_backlog with the given parameters.

        Returns the item info dict (with 'item_number', 'filename', 'filepath'),
        or None if the callback is not configured.

        Args:
            item_type: "feature" or "defect".
            title: Backlog item title.
            body: Backlog item description.
            user: Slack user who submitted the request.
            ts: Slack message timestamp.
        """
        if self._callbacks.create_backlog:
            return self._callbacks.create_backlog(item_type, title, body, user, ts)
        return None

    def _run_dedup_check(
        self,
        intake: IntakeState,
        title: str,
        description: str,
        high_sim: list[dict],
        rag: object,
    ) -> bool:
        """Run LLM-based deduplication check against high-similarity RAG hits.

        If the LLM confirms a duplicate, appends new information to the
        existing item and notifies the user.

        Args:
            intake: Current intake state.
            title: Parsed item title.
            description: Built item description.
            high_sim: List of high-similarity RAG results.
            rag: RAG instance for updating the existing item.

        Returns:
            True if the item is a duplicate (caller should skip creation).
        """
        candidates_text = "\n".join(
            f"- {s['title']} (similarity: {s['similarity']:.2f}, file: {s['filename']})"
            for s in high_sim
        )
        dedup_prompt = (
            f"A new {intake.item_type} request was submitted:\n"
            f"Title: {title}\n"
            f"Description: {description[:400]}\n\n"
            f"These existing items are similar:\n{candidates_text}\n\n"
            f"Is this new request a duplicate of any existing item? "
            f"Respond with ONLY a JSON object:\n"
            f'- {{"duplicate": true, "match_filename": "..."}} if duplicate\n'
            f'- {{"duplicate": false}} if not a duplicate'
        )
        try:
            dedup_response = (
                self._callbacks.call_claude(dedup_prompt, "haiku", 30).text
                if self._callbacks.call_claude
                else ""
            )
            if dedup_response:
                dedup_result = json.loads(dedup_response)
                if isinstance(dedup_result, dict) and dedup_result.get("duplicate"):
                    match_file = dedup_result.get("match_filename", "")
                    match_item = next(
                        (s for s in high_sim if s["filename"] == match_file),
                        high_sim[0],
                    )
                    existing_path = match_item["filepath"]
                    if os.path.isfile(existing_path):
                        with open(existing_path, "a") as ef:
                            ef.write(
                                f"\n\n## Additional Report\n\n"
                                f"**From:** {intake.user} at {intake.ts}\n\n"
                                f"{description[:500]}\n"
                            )
                        with open(existing_path) as ef:
                            rag.update_item(existing_path, ef.read())
                    if self._callbacks.send_status:
                        self._callbacks.send_status(
                            f"*Consolidated with existing item:* `{match_item['filename']}`\n"
                            "_New information appended._",
                            "success",
                            intake.channel_id,
                        )
                    return True
        except (json.JSONDecodeError, Exception) as e:
            print(f"[RAG] Dedup check failed, proceeding: {e}")
        return False


# ── Module-level helper ───────────────────────────────────────────────────────


def _format_item_ref(item_info: Optional[dict]) -> str:
    """Format a backlog item reference for Slack notification messages.

    Args:
        item_info: Dict with 'item_number' and 'filename' keys, or None.

    Returns:
        Formatted string like " (#3 - `03-my-feature.md`)", or empty string.
    """
    if not item_info:
        return ""
    return f" (#{item_info['item_number']} - `{item_info['filename']}`)"
