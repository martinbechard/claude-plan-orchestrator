# langgraph_pipeline/slack/__init__.py
# SlackNotifier facade: composes identity, notifier, poller, and suspension submodules.
# Design: docs/plans/2026-02-26-03-extract-slack-modules-design.md

"""SlackNotifier facade exposing the same public API as the original monolithic class.

Composes four submodule classes — SlackNotifier (notifier.py), SlackPoller
(poller.py), and SlackSuspension (suspension.py) — wired together via callback
objects so existing scripts require no changes.

Public re-exports: SlackNotifier, AgentIdentity, load_agent_identity, IntakeState.
"""

import threading
from typing import Callable, Optional

from langgraph_pipeline.slack.identity import (
    AgentIdentity,
    load_agent_identity,
)
from langgraph_pipeline.slack.notifier import SLACK_CONFIG_PATH
from langgraph_pipeline.slack.notifier import SlackNotifier as _SlackNotifierImpl
from langgraph_pipeline.slack.poller import PollerCallbacks, SlackPoller
from langgraph_pipeline.slack.suspension import (
    IntakeState,
    SlackSuspension,
    SuspensionCallbacks,
)

__all__ = ["SlackNotifier", "AgentIdentity", "load_agent_identity", "IntakeState"]


class SlackNotifier:
    """Facade that composes the four Slack submodule classes into one object.

    Exposes the same public API as the original monolithic SlackNotifier so
    plan-orchestrator.py and auto-pipeline.py require no changes when they
    import from langgraph_pipeline.slack instead of defining the class inline.

    Internal delegation:
    - Config loading, outbound messaging, Block Kit formatting → _notifier
    - Inbound polling, loop prevention, backlog creation → _poller
    - Question/answer flows, 5-Whys intake analysis → _suspension
    - Agent identity and message signing → _notifier (via IdentityMixin)
    """

    def __init__(
        self,
        config_path: str = SLACK_CONFIG_PATH,
        *,
        call_claude: Optional[Callable] = None,
        gather_state: Optional[Callable] = None,
        format_state: Optional[Callable] = None,
        rag: Optional[object] = None,
    ) -> None:
        """Initialize the facade and wire all submodule callbacks.

        Args:
            config_path: Path to slack.local.yaml config file.
            call_claude: LLM invocation callback — (prompt, model, timeout) -> str.
            gather_state: Pipeline state gatherer — () -> dict.
            format_state: State formatter — (state) -> str.
            rag: RAG instance for duplicate detection (duck-typed).
        """
        # Shared state: intake lock and pending intakes dict used by both
        # poller (to register new intakes) and suspension (to complete them).
        self._intake_lock = threading.Lock()
        self._pending_intakes: dict = {}

        # ── Notifier: config loading + outbound messaging ─────────────────────
        self._notifier = _SlackNotifierImpl(config_path)

        # ── Suspension: Q&A flows and 5-Whys intake analysis ─────────────────
        # Lambda closures break the poller↔suspension circular dependency:
        # suspension.create_backlog needs self._poller, which doesn't exist yet.
        # The lambda defers attribute lookup until the first call.
        question_config = self._notifier._notify_config.get("questions", {})
        suspension_callbacks = SuspensionCallbacks(
            post_message=self._notifier._post_message,
            post_message_ts=self._notifier._post_message_get_ts,
            build_block=self._notifier._build_status_block,
            truncate=self._notifier._truncate_for_slack,
            send_status=self._notifier.send_status,
            get_type_channel=self._notifier.get_type_channel_id,
            sign_text=self._notifier._sign_text,
            as_role=self._notifier._as_role,
            ensure_socket_mode=self._notifier._ensure_socket_mode,
            should_notify=self._notifier._should_notify,
            call_claude=call_claude,
            gather_state=gather_state,
            format_state=format_state,
            create_backlog=lambda *a, **kw: self._poller.create_backlog_item(*a, **kw),
            check_intake_rate=lambda: self._poller._check_intake_rate_limit(),
            record_intake=lambda: self._poller._record_intake_timestamp(),
            intake_lock=self._intake_lock,
            pending_intakes=self._pending_intakes,
            rag=rag,
        )
        self._suspension = SlackSuspension(
            bot_token=self._notifier._bot_token,
            question_config=question_config,
            callbacks=suspension_callbacks,
        )

        # ── Poller: inbound polling, routing, and loop prevention ─────────────
        poller_callbacks = PollerCallbacks(
            call_claude=call_claude,
            post_message=self._notifier._post_message,
            build_block=self._notifier._build_status_block,
            send_status=self._notifier.send_status,
            run_intake=self._suspension._run_intake_analysis,
            answer_question=self._suspension.answer_question,
            check_suspensions=self._suspension._check_all_suspensions,
            intake_lock=self._intake_lock,
            pending_intakes=self._pending_intakes,
        )
        self._poller = SlackPoller(
            bot_token=self._notifier._bot_token,
            channel_id=self._notifier._channel_id,
            channel_prefix=self._notifier._channel_prefix,
            enabled=self._notifier._enabled,
            callbacks=poller_callbacks,
        )

        # Share the sent-ts set so both notifier and poller track sent messages
        # for deduplication (notifier records outbound ts; poller filters inbound).
        self._poller._own_sent_ts = self._notifier._own_sent_ts

    # ── Identity API ──────────────────────────────────────────────────────────

    def set_identity(self, identity: AgentIdentity, role: str) -> None:
        """Configure agent identity for message signing and inbound filtering.

        Propagates to both the notifier (outbound signing) and the poller
        (filtering inbound self-addressed messages by agent name).

        Args:
            identity: The AgentIdentity for this project.
            role: The agent role constant (e.g., AGENT_ROLE_ORCHESTRATOR).
        """
        self._notifier.set_identity(identity, role)
        self._poller._agent_identity = identity

    # ── Notifier API ──────────────────────────────────────────────────────────

    def is_enabled(self) -> bool:
        """Return True if Slack notifications are enabled and configured."""
        return self._notifier.is_enabled()

    def send_status(
        self, message: str, level: str = "info", channel_id: Optional[str] = None
    ) -> None:
        """Send a status update to Slack. No-op if disabled.

        Args:
            message: Status message text.
            level: Message level (info, success, error, warning).
            channel_id: Target channel override. Falls back to notifications channel.
        """
        self._notifier.send_status(message, level, channel_id)

    def send_defect(self, title: str, description: str, file_path: str = "") -> None:
        """Send a defect report to Slack.

        Args:
            title: Defect title.
            description: Defect description.
            file_path: Optional file path where defect was found.
        """
        self._notifier.send_defect(title, description, file_path)

    def send_idea(self, title: str, description: str) -> None:
        """Send a feature idea to Slack.

        Args:
            title: Idea title.
            description: Idea description.
        """
        self._notifier.send_idea(title, description)

    def process_agent_messages(self, status: dict) -> None:
        """Process slack_messages from a task-status.json dict.

        Args:
            status: Task status dict potentially containing slack_messages field.
        """
        self._notifier.process_agent_messages(status)

    def get_type_channel_id(self, item_type: str) -> str:
        """Return the channel ID for a type-specific channel.

        Args:
            item_type: One of 'feature', 'defect', or 'analysis'.

        Returns:
            Channel ID string, or empty string if not found or disabled.
        """
        return self._notifier.get_type_channel_id(item_type)

    # ── Poller API ────────────────────────────────────────────────────────────

    def poll_messages(self) -> list[dict]:
        """Fetch unread messages from all prefix-* channels.

        Returns:
            List of message dicts tagged with _channel_name and _channel_id.
        """
        return self._poller.poll_messages()

    def start_background_polling(self) -> None:
        """Start a background thread that polls Slack for inbound messages."""
        self._poller.start_background_polling()

    def stop_background_polling(self) -> None:
        """Stop the background polling thread gracefully."""
        self._poller.stop_background_polling()

    def create_backlog_item(
        self,
        item_type: str,
        title: str,
        body: str,
        user: str = "",
        ts: str = "",
    ) -> dict[str, str | int]:
        """Create a backlog markdown file from a Slack message.

        Args:
            item_type: 'feature' or 'defect'.
            title: Item title.
            body: Item description.
            user: Slack user ID who sent the message.
            ts: Message timestamp.

        Returns:
            Dict with filepath, filename, item_number on success, or empty dict.
        """
        return self._poller.create_backlog_item(item_type, title, body, user, ts)

    def handle_control_command(
        self,
        command: str,
        classification: str,
        channel_id: Optional[str] = None,
    ) -> None:
        """Handle a control command from Slack.

        Args:
            command: The original message text.
            classification: One of 'control_stop', 'control_skip', 'info_request'.
            channel_id: Reply to this channel. Falls back to default.
        """
        self._poller.handle_control_command(command, classification, channel_id)

    # ── Suspension API ────────────────────────────────────────────────────────

    def send_question(
        self,
        question: str,
        options: list[str],
        timeout_minutes: int = 0,
    ) -> Optional[str]:
        """Send a question to Slack and wait for a human answer.

        Args:
            question: Question text to display.
            options: List of valid answer options.
            timeout_minutes: Timeout in minutes (0 = use config default).

        Returns:
            Answer string if received, configured fallback value on timeout, None on error.
        """
        return self._suspension.send_question(question, options, timeout_minutes)

    def post_suspension_question(
        self,
        slug: str,
        item_type: str,
        question: str,
        question_context: str,
    ) -> Optional[str]:
        """Post a suspension question to the type-specific Slack channel.

        Args:
            slug: Work item slug (e.g., '9-ux-feature').
            item_type: 'feature' or 'defect'.
            question: The question text.
            question_context: Why this information is needed.

        Returns:
            Message ts (thread_ts) for reply correlation, None on failure.
        """
        return self._suspension.post_suspension_question(
            slug, item_type, question, question_context
        )

    def check_suspension_reply(
        self,
        channel_id: str,
        thread_ts: str,
    ) -> Optional[str]:
        """Check for a human reply in a Slack thread.

        Args:
            channel_id: Slack channel ID containing the thread.
            thread_ts: Timestamp of the original question message (thread root).

        Returns:
            Text of the first human reply if found, None otherwise.
        """
        return self._suspension.check_suspension_reply(channel_id, thread_ts)

    def answer_question(
        self, question: str, channel_id: Optional[str] = None
    ) -> None:
        """Answer a Slack question using pipeline state as context.

        Args:
            question: The question text to answer.
            channel_id: Channel to post the answer to.
        """
        self._suspension.answer_question(question, channel_id=channel_id)

    def _run_intake_analysis(self, intake: IntakeState) -> None:
        """Run 5-Whys intake analysis for a new backlog request.

        Args:
            intake: IntakeState describing the incoming Slack message.
        """
        self._suspension._run_intake_analysis(intake)
