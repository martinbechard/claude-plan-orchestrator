# langgraph_pipeline/slack/notifier.py
# Message posting, channel discovery, and outbound formatting for Slack.
# Design: docs/plans/2026-02-26-03-extract-slack-modules-design.md

"""SlackNotifier: outbound Slack messaging, channel discovery, and event routing.

Extracted from plan-orchestrator.py SlackNotifier class (~line 3623).
Covers config loading, HTTP message posting, Block Kit formatting,
channel discovery/caching, and high-level send methods.
"""

import json
import time
import urllib.parse
import urllib.request
from typing import Optional

import yaml

from langgraph_pipeline.slack.identity import AgentIdentity, IdentityMixin

# ── Optional Socket Mode support ────────────────────────────────────────────

try:
    from slack_bolt import App
    from slack_bolt.adapter.socket_mode import SocketModeHandler
    SOCKET_MODE_AVAILABLE = True
except ImportError:
    SOCKET_MODE_AVAILABLE = False
    App = None  # type: ignore[assignment,misc]
    SocketModeHandler = None  # type: ignore[assignment,misc]

# ── Constants ────────────────────────────────────────────────────────────────

SLACK_CONFIG_PATH = ".claude/slack.local.yaml"

SLACK_CHANNEL_PREFIX = "orchestrator-"

SLACK_CHANNEL_ROLE_SUFFIXES: dict[str, str] = {
    "features": "feature",
    "defects": "defect",
    "questions": "question",
    "notifications": "control",
    "reports": "analysis",
}

SLACK_CHANNEL_CACHE_SECONDS = 300

SLACK_BLOCK_TEXT_MAX_LENGTH = 2900

SLACK_LEVEL_EMOJI: dict[str, str] = {
    "info": ":large_blue_circle:",
    "success": ":white_check_mark:",
    "error": ":x:",
    "warning": ":warning:",
    "question": ":question:",
}

# A5 classification hint: automated pipeline notifications should be "none"
MESSAGE_ROUTING_PROMPT = """You are a message router for a CI/CD pipeline orchestrator.
A user sent this message via Slack: "{text}"

Decide the appropriate action. Respond with ONLY a JSON object:

Available actions:
- {{"action": "stop_pipeline"}} - User explicitly wants to stop/pause the pipeline
- {{"action": "skip_item"}} - User wants to skip the current work item
- {{"action": "get_status"}} - User wants pipeline status information
- {{"action": "create_feature", "title": "...", "body": "..."}} - User is requesting a new feature
- {{"action": "create_defect", "title": "...", "body": "..."}} - User is reporting a bug/defect
- {{"action": "ask_question", "question": "..."}} - User is asking a question
- {{"action": "none"}} - Message doesn't require any pipeline action

Be conservative: only use stop_pipeline if the user clearly intends to stop.
A message like "stop doing X" is NOT a stop command.

IMPORTANT: Messages that contain status emoji (:white_check_mark:, :large_blue_circle:, :x:,
:warning:) followed by phrases like "Defect received", "Feature received", "Feature created",
"Defect created", or "Received your defect/feature request" are automated pipeline notifications.
These should ALWAYS be classified as {{"action": "none"}}."""

# ── SlackNotifier ────────────────────────────────────────────────────────────


class SlackNotifier(IdentityMixin):
    """Outbound Slack messaging: config loading, HTTP posting, and send methods.

    Reads .claude/slack.local.yaml on init. If the file is missing or
    slack.enabled is false, all methods are no-ops (silent, no errors).
    Uses urllib.request (stdlib only) for HTTP POST with Bearer token auth.

    Inherits IdentityMixin for agent identity and message signing.
    """

    def __init__(self, config_path: str = SLACK_CONFIG_PATH) -> None:
        """Initialize SlackNotifier from config file.

        Args:
            config_path: Path to slack.local.yaml config file.
        """
        IdentityMixin.__init__(self)

        self._enabled = False
        self._bot_token = ""
        self._app_token = ""
        self._channel_id = ""
        self._notify_config: dict = {}
        self._socket_handler = None
        self._discovered_channels: dict[str, str] = {}
        self._channels_discovered_at = 0.0
        self._channel_prefix = SLACK_CHANNEL_PREFIX
        self._own_sent_ts: set[str] = set()
        self._channels_logged: bool = False

        try:
            with open(config_path, "r") as f:
                config = yaml.safe_load(f)

            if not isinstance(config, dict):
                return

            slack_config = config.get("slack", {})
            if not isinstance(slack_config, dict):
                return

            self._enabled = slack_config.get("enabled", False)
            if not self._enabled:
                return

            self._bot_token = slack_config.get("bot_token", "")
            self._app_token = slack_config.get("app_token", "")
            self._channel_id = slack_config.get("channel_id", "")
            self._notify_config = slack_config.get("notify", {})

            prefix = slack_config.get("channel_prefix", "")
            if prefix:
                if not prefix.endswith("-"):
                    prefix += "-"
                self._channel_prefix = prefix

        except (IOError, yaml.YAMLError):
            # Config file missing or invalid — remain disabled
            pass

    # ── Public state accessors ───────────────────────────────────────────────

    def is_enabled(self) -> bool:
        """Return True if Slack notifications are enabled and configured."""
        return self._enabled

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _should_notify(self, event: str) -> bool:
        """Return True if a specific notify event is enabled in config.

        Args:
            event: Event key (e.g., "on_task_complete", "on_defect_found").
        """
        return self._enabled and self._notify_config.get(event, False)

    def _ensure_socket_mode(self) -> bool:
        """Start Socket Mode handler if available and not already running.

        Returns:
            True if Socket Mode is available and connected, False otherwise.
        """
        if not SOCKET_MODE_AVAILABLE:
            return False
        if self._socket_handler is not None:
            return True
        if not self._app_token:
            return False

        try:
            app = App(token=self._bot_token)

            @app.action("orchestrator_answer_.*")
            def handle_answer(ack, action, body):  # noqa: ARG001
                ack()

            handler = SocketModeHandler(app, self._app_token)
            handler.connect()
            self._socket_handler = handler
            return True
        except Exception as e:
            print(f"[SLACK] Socket Mode failed to start: {e}")
            return False

    # ── HTTP posting ─────────────────────────────────────────────────────────

    def _post_message(self, payload: dict, channel_id: Optional[str] = None) -> bool:
        """POST a message to Slack via chat.postMessage API.

        Uses urllib.request with Bearer token auth. Returns True on success.
        Catches all exceptions and logs errors without raising.

        Args:
            payload: Slack Block Kit payload dict.
            channel_id: Target channel. Falls back to self._channel_id.
        """
        target = channel_id or self._channel_id
        if not self._bot_token or not target:
            return False

        payload["channel"] = target

        try:
            req = urllib.request.Request(
                "https://slack.com/api/chat.postMessage",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "Authorization": f"Bearer {self._bot_token}",
                },
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read())
                if result.get("ok", False):
                    sent_ts = result.get("ts")
                    if sent_ts:
                        self._own_sent_ts.add(sent_ts)
                    return True
                return False
        except Exception as e:
            print(f"[SLACK] Failed to post message: {e}")
            return False

    def _post_message_get_ts(
        self, payload: dict, channel_id: Optional[str] = None
    ) -> Optional[str]:
        """POST a message to Slack and return the message timestamp.

        Same as _post_message() but returns the message ts on success instead
        of a boolean. The ts is used as thread_ts for reply correlation.

        Args:
            payload: Slack Block Kit payload dict.
            channel_id: Target channel. Falls back to self._channel_id.

        Returns:
            Message ts string if successful, None otherwise.
        """
        target = channel_id or self._channel_id
        if not self._bot_token or not target:
            return None

        payload["channel"] = target

        try:
            req = urllib.request.Request(
                "https://slack.com/api/chat.postMessage",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "Authorization": f"Bearer {self._bot_token}",
                },
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read())
                if result.get("ok", False):
                    msg_ts = result.get("ts")
                    if msg_ts:
                        self._own_sent_ts.add(msg_ts)
                    return msg_ts
                print(f"[SLACK] Post message error: {result.get('error', 'unknown')}")
                return None
        except Exception as e:
            print(f"[SLACK] Failed to post message: {e}")
            return None

    # ── Block Kit formatting ─────────────────────────────────────────────────

    def _build_status_block(self, message: str, level: str) -> dict:
        """Build a Slack Block Kit payload for a status message.

        Args:
            message: Message text (supports Slack mrkdwn).
            level: Message level (info, success, error, warning, question).

        Returns:
            Slack Block Kit payload dict.
        """
        emoji = SLACK_LEVEL_EMOJI.get(level, ":large_blue_circle:")
        signature = ""
        if self._agent_identity and self._active_role:
            name = self._agent_identity.name_for_role(self._active_role)
            signature = f" \u2014 *{name}*"
        body_max = SLACK_BLOCK_TEXT_MAX_LENGTH - len(signature)
        full_text = self._truncate_for_slack(f"{emoji} {message}", body_max) + signature
        return {
            "blocks": [
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": full_text},
                }
            ]
        }

    @staticmethod
    def _truncate_for_slack(
        text: str, max_length: int = SLACK_BLOCK_TEXT_MAX_LENGTH
    ) -> str:
        """Truncate text to fit Slack Block Kit section text limit.

        If text exceeds max_length, truncates and appends an indicator
        showing how many characters were omitted.

        Args:
            text: Message text to truncate.
            max_length: Maximum allowed length (default SLACK_BLOCK_TEXT_MAX_LENGTH).
        """
        if len(text) <= max_length:
            return text
        omitted = len(text) - max_length + 40
        return text[: max_length - 40] + f"\n_...({omitted} chars omitted)_"

    # ── Channel discovery ────────────────────────────────────────────────────

    def _discover_channels(self) -> dict[str, str]:
        """Discover prefix-* channels the bot is a member of.

        Returns dict of channel_name -> channel_id. Caches results for
        SLACK_CHANNEL_CACHE_SECONDS to avoid excessive API calls.
        """
        now = time.time()
        if (
            self._discovered_channels
            and now - self._channels_discovered_at < SLACK_CHANNEL_CACHE_SECONDS
        ):
            return self._discovered_channels

        try:
            params = urllib.parse.urlencode(
                {"types": "public_channel,private_channel", "limit": "100"}
            )
            req = urllib.request.Request(
                f"https://slack.com/api/users.conversations?{params}",
                headers={"Authorization": f"Bearer {self._bot_token}"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read())

            if not result.get("ok", False):
                print(f"[SLACK] Channel discovery error: {result.get('error', 'unknown')}")
                return self._discovered_channels

            channels: dict[str, str] = {}
            for ch in result.get("channels", []):
                name = ch.get("name", "")
                if name.startswith(self._channel_prefix):
                    channels[name] = ch["id"]

            self._discovered_channels = channels
            self._channels_discovered_at = now
            if channels and not self._channels_logged:
                print(
                    f"[SLACK] Discovered channels: "
                    f"{', '.join(f'#{n}' for n in sorted(channels))}"
                )
                self._channels_logged = True
            return channels

        except Exception as e:
            print(f"[SLACK] Channel discovery failed: {e}")
            return self._discovered_channels

    def _get_notifications_channel_id(self) -> str:
        """Return the channel ID for the notifications channel.

        Looks up the <prefix>notifications channel from discovered channels.
        Falls back to the legacy single channel_id.
        """
        notifications_name = f"{self._channel_prefix}notifications"
        channels = self._discover_channels()
        return channels.get(notifications_name, self._channel_id)

    def get_type_channel_id(self, item_type: str) -> str:
        """Return the channel ID for a type-specific channel.

        Maps item_type ('feature', 'defect', 'analysis') to the corresponding
        Slack channel using the _discover_channels() infrastructure.

        Returns empty string if the channel is not found or Slack is disabled.

        Args:
            item_type: One of 'feature', 'defect', or 'analysis'.
        """
        suffix_map = {"feature": "features", "defect": "defects", "analysis": "reports"}
        suffix = suffix_map.get(item_type, "")
        if not suffix:
            return ""
        channel_name = f"{self._channel_prefix}{suffix}"
        channels = self._discover_channels()
        return channels.get(channel_name, "")

    # ── High-level send methods ──────────────────────────────────────────────

    def send_status(
        self, message: str, level: str = "info", channel_id: Optional[str] = None
    ) -> None:
        """Send a status update to Slack. No-op if disabled.

        Args:
            message: Status message text.
            level: Message level (info, success, error, warning).
            channel_id: Target channel override. Falls back to notifications channel.
        """
        target = channel_id or self._get_notifications_channel_id()
        if not self._enabled or not self._bot_token or not target:
            return
        payload = self._build_status_block(message, level)
        self._post_message(payload, channel_id=target)

    def send_defect(self, title: str, description: str, file_path: str = "") -> None:
        """Send a defect report to Slack.

        Args:
            title: Defect title.
            description: Defect description.
            file_path: Optional file path where defect was found.
        """
        if not self._should_notify("on_defect_found"):
            return
        msg = f":beetle: *Defect found:* {title}"
        if file_path:
            msg += f"\n`{file_path}`"
        if description:
            msg += f"\n{description}"
        self._post_message(self._build_status_block(msg, "error"))

    def send_idea(self, title: str, description: str) -> None:
        """Send a feature idea to Slack.

        Args:
            title: Idea title.
            description: Idea description.
        """
        if not self._should_notify("on_idea_found"):
            return
        msg = f":bulb: *Idea:* {title}"
        if description:
            msg += f"\n{description}"
        self._post_message(self._build_status_block(msg, "info"))

    def process_agent_messages(self, status: dict) -> None:
        """Process slack_messages from a task-status.json dict.

        Iterates over the 'slack_messages' list in the status dict and
        dispatches each message to the appropriate send method.

        Args:
            status: Task status dict potentially containing slack_messages field.
        """
        messages = status.get("slack_messages", [])
        for msg in messages:
            msg_type = msg.get("type", "")
            title = msg.get("title", "")
            desc = msg.get("description", "")
            if msg_type == "defect":
                self.send_defect(title, desc, msg.get("file_path", ""))
            elif msg_type == "idea":
                self.send_idea(title, desc)
