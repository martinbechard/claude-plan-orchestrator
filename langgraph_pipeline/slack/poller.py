# langgraph_pipeline/slack/poller.py
# Inbound Slack polling and loop-prevention safety layers A1-A4.
# Design: docs/plans/2026-02-26-03-extract-slack-modules-design.md

"""SlackPoller: inbound message polling and deduplication.

Extracted from plan-orchestrator.py SlackNotifier class (~line 4313).
Covers channel polling, last-read tracking, message deduplication, and
four safety layers that prevent bot-induced feedback loops:

  A1 - Chain-loop artifact detection (on-disk intake history)
  A2 - Self-reply window circuit breaker (in-memory, per-channel)
  A3 - Content-based bot-notification pattern filter (regex)
  A4 - Global intake rate limiter (in-memory sliding window)

Cross-module operations (message posting, intake analysis, Q&A) are
injected via PollerCallbacks so this class remains independently testable.
"""

import json
import logging
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

from langgraph_pipeline.slack.identity import AGENT_ADDRESS_PATTERN, AgentIdentity
from langgraph_pipeline.slack.suspension import IntakeState

# ── Constants ────────────────────────────────────────────────────────────────

SLACK_LAST_READ_PATH = ".claude/slack-last-read.json"
SLACK_INBOUND_POLL_LIMIT = 20
SLACK_POLL_INTERVAL_SECONDS = 15

# A2: Self-reply loop detection
MAX_SELF_REPLIES_PER_WINDOW = 1
LOOP_DETECTION_WINDOW_SECONDS = 300  # 5-minute sliding window

# Dedup TTL
MESSAGE_TRACKING_TTL_SECONDS = 3600

# A3: Content-based notification pattern filter
BOT_NOTIFICATION_PATTERN = re.compile(
    r"(?:"
    r"(?::white_check_mark:|:large_blue_circle:|:x:|:warning:|:question:)\s*"
    r"\*?(?:Defect|Feature)\s+(?:received|created)\*?"
    r"|"
    r"(?::white_check_mark:|:large_blue_circle:|:x:|:warning:)\s*"
    r"\*?(?:Completed:|Pipeline:\s*(?:processing|completed|failed|skipped))\*?"
    r"|"
    r"Received\s+your\s+(?:defect|feature)\s+request"
    r")",
    re.IGNORECASE,
)

# A4: Global intake rate limiter
MAX_INTAKES_PER_WINDOW = 10
INTAKE_RATE_WINDOW_SECONDS = 300  # 5-minute sliding window

# A1: Chain detection history file
INTAKE_HISTORY_PATH = ".claude/plans/.intake-history.json"
INTAKE_HISTORY_MAX_ENTRIES = 100
INTAKE_HISTORY_TTL_SECONDS = 3600  # 1 hour

# Disk-persisted backlog creation throttle
BACKLOG_CREATION_THROTTLE_PATH = ".claude/plans/.backlog-creation-throttle.json"
MAX_DEFECTS_PER_HOUR = 20
MAX_FEATURES_PER_HOUR = 20
BACKLOG_THROTTLE_WINDOW_SECONDS = 3600  # 1-hour sliding window

STOP_SEMAPHORE_PATH = ".claude/plans/.stop"
MESSAGE_ROUTING_TIMEOUT_SECONDS = 30
MINIMUM_INTAKE_MESSAGE_LENGTH = 20

# Pattern to find JSON object in LLM response (handles markdown code fences)
_JSON_BLOCK_PATTERN = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_JSON_INLINE_PATTERN = re.compile(r"(\{[^{}]*\})")


def _extract_json(text: str) -> Any:
    """Extract a JSON object from LLM text that may include explanation or code fences.

    Tries in order:
    1. Direct json.loads (response is pure JSON)
    2. JSON inside markdown code fences
    3. First inline { ... } block
    """
    text = text.strip()
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass

    # Try markdown code fence
    match = _JSON_BLOCK_PATTERN.search(text)
    if match:
        try:
            return json.loads(match.group(1))
        except (json.JSONDecodeError, ValueError):
            pass

    # Try first inline JSON object
    match = _JSON_INLINE_PATTERN.search(text)
    if match:
        try:
            return json.loads(match.group(1))
        except (json.JSONDecodeError, ValueError):
            pass

    return None

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

# Channel role suffix mapping (mirrored from notifier constants)
SLACK_CHANNEL_ROLE_SUFFIXES: dict[str, str] = {
    "features": "feature",
    "defects": "defect",
    "questions": "question",
    "notifications": "control",
    "reports": "analysis",
}

SLACK_CHANNEL_CACHE_SECONDS = 300

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


# ── Helpers ───────────────────────────────────────────────────────────────────


def _safe_float_ts(ts: str) -> float:
    """Parse a Slack message ts string to float for age comparisons.

    Slack ts values are Unix timestamp strings like '1234567890.123456'.
    Returns 0.0 on parse failure so the entry is treated as expired.

    Args:
        ts: Slack message timestamp string.
    """
    try:
        return float(ts)
    except (ValueError, TypeError):
        return 0.0


# ── PollerCallbacks ───────────────────────────────────────────────────────────


@dataclass
class PollerCallbacks:
    """Cross-module callbacks injected into SlackPoller.

    All fields are optional. Missing callbacks result in no-ops or
    fallback behaviour so the poller can be tested incrementally.

    Attributes:
        call_claude: LLM routing call — (prompt, model, timeout) -> str.
        post_message: Slack HTTP post — (payload, channel_id) -> bool.
        build_block: Block Kit formatter — (message, level) -> dict.
        send_status: Status notifier — (message, level, channel_id) -> None.
        run_intake: Intake analysis starter — (intake: IntakeState) -> None.
        answer_question: Q&A responder — (question, *, channel_id) -> None.
        check_suspensions: Suspension checker — () -> None.
        intake_lock: Shared lock protecting pending_intakes.
        pending_intakes: Shared dict of active IntakeState by key.
    """

    call_claude: Optional[Callable] = None
    post_message: Optional[Callable] = None
    build_block: Optional[Callable] = None
    send_status: Optional[Callable] = None
    run_intake: Optional[Callable] = None
    answer_question: Optional[Callable] = None
    check_suspensions: Optional[Callable] = None
    intake_lock: Optional[threading.Lock] = None
    pending_intakes: Optional[dict] = None


# ── SlackPoller ───────────────────────────────────────────────────────────────


class SlackPoller:
    """Inbound Slack polling with loop-prevention safety layers A1-A4.

    Handles channel discovery, per-channel last-read tracking, message
    deduplication, and routing of polled messages. Cross-module operations
    (message posting, intake analysis, Q&A) are injected via PollerCallbacks.

    Safety layers:
      A1 - Chain-loop artifact detection via on-disk intake history
      A2 - Self-reply window circuit breaker (per-channel, in-memory)
      A3 - Content-based bot-notification pattern filter (regex)
      A4 - Global intake rate limiter (in-memory sliding window)
    """

    def __init__(
        self,
        bot_token: str,
        channel_id: str,
        channel_prefix: str,
        enabled: bool,
        callbacks: Optional[PollerCallbacks] = None,
        agent_identity: Optional[AgentIdentity] = None,
    ) -> None:
        """Initialize SlackPoller with connection params and callbacks.

        Args:
            bot_token: Slack bot OAuth token.
            channel_id: Legacy single-channel fallback ID.
            channel_prefix: Prefix for orchestrator channels (e.g. 'orchestrator-').
            enabled: Whether polling is active.
            callbacks: Cross-module operation callbacks.
            agent_identity: Agent identity for addressing/loop detection.
        """
        self._bot_token = bot_token
        self._channel_id = channel_id
        self._channel_prefix = channel_prefix
        self._enabled = enabled
        self._callbacks = callbacks or PollerCallbacks()
        self._agent_identity = agent_identity

        # Channel discovery cache
        self._discovered_channels: dict[str, str] = {}
        self._channels_discovered_at = 0.0

        # Dedup state
        self._processed_message_ts: set[str] = set()
        self._own_sent_ts: set[str] = set()

        # A2: Self-reply window (channel_id -> list of monotonic timestamps)
        self._self_reply_window: dict[str, list[float]] = {}

        # A4: Global intake rate limiter
        self._intake_timestamps: list[float] = []

        # A1: Chain detection history (loaded from disk on start)
        self._intake_history: list[dict] = []

        # Background polling thread
        self._poll_thread: Optional[threading.Thread] = None
        self._poll_stop_event = threading.Event()

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
            if channels:
                print(
                    f"[SLACK] Discovered channels: "
                    f"{', '.join(f'#{n}' for n in sorted(channels))}"
                )
            return channels

        except Exception as e:
            print(f"[SLACK] Channel discovery failed: {e}")
            return self._discovered_channels

    def _get_channel_role(self, channel_name: str) -> str:
        """Get the role for a channel name based on its suffix.

        Strips the configured prefix and looks up the remaining suffix
        in SLACK_CHANNEL_ROLE_SUFFIXES.

        Args:
            channel_name: Full channel name (e.g. 'orchestrator-features').

        Returns:
            Role string (e.g. 'feature', 'defect') or empty string if unrecognised.
        """
        if not channel_name.startswith(self._channel_prefix):
            return ""
        suffix = channel_name[len(self._channel_prefix):]
        return SLACK_CHANNEL_ROLE_SUFFIXES.get(suffix, "")

    # ── Last-read persistence ────────────────────────────────────────────────

    def _load_last_read_all(self) -> dict[str, str]:
        """Load per-channel last-read timestamps from disk.

        Returns dict of channel_id -> last_ts. Empty dict on first run.
        """
        try:
            with open(SLACK_LAST_READ_PATH, "r") as f:
                data = json.load(f)
            # Handle legacy single-channel format
            if "channels" in data:
                return data["channels"]
            if "channel_id" in data and "last_ts" in data:
                return {data["channel_id"]: data["last_ts"]}
            return {}
        except (IOError, json.JSONDecodeError):
            return {}

    def _save_last_read_all(self, channels: dict[str, str]) -> None:
        """Persist per-channel last-read timestamps to disk.

        Args:
            channels: Dict of channel_id -> last_ts to persist.
        """
        try:
            with open(SLACK_LAST_READ_PATH, "w") as f:
                json.dump({"channels": channels}, f)
        except IOError as e:
            print(f"[SLACK] Failed to save last-read state: {e}")

    # ── Polling ──────────────────────────────────────────────────────────────

    def poll_messages(self) -> list[dict]:
        """Fetch unread messages from all prefix-* channels.

        Discovers channels by prefix, polls each for new messages,
        tags each message with its source channel name for routing.
        Falls back to the single channel_id if no prefix-* channels found.

        Returns:
            List of message dicts, each tagged with _channel_name and _channel_id.
        """
        if not self._enabled or not self._bot_token:
            return []

        channels = self._discover_channels()
        # Fall back to legacy single channel if no orchestrator-* channels found
        if not channels and self._channel_id:
            channels = {"orchestrator": self._channel_id}

        if not channels:
            return []

        last_read = self._load_last_read_all()
        all_messages: list[dict] = []
        updated_last_read = dict(last_read)

        for channel_name, channel_id in channels.items():
            last_ts = last_read.get(channel_id, "")

            # On first run for this channel, seed with 1 hour ago to capture
            # recent messages without flooding with old history
            if not last_ts:
                last_ts = f"{time.time() - 3600:.6f}"
                updated_last_read[channel_id] = last_ts

            try:
                params = urllib.parse.urlencode(
                    {
                        "channel": channel_id,
                        "oldest": last_ts,
                        "limit": SLACK_INBOUND_POLL_LIMIT,
                        "inclusive": "false",
                    }
                )
                req = urllib.request.Request(
                    f"https://slack.com/api/conversations.history?{params}",
                    headers={"Authorization": f"Bearer {self._bot_token}"},
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    result = json.loads(resp.read())

                if not result.get("ok", False):
                    print(
                        f"[SLACK] Error polling #{channel_name}: "
                        f"{result.get('error', 'unknown')}"
                    )
                    continue

                messages = result.get("messages", [])
                if not messages:
                    continue

                # Update last-read for this channel (newest first in result)
                updated_last_read[channel_id] = messages[0].get("ts", last_ts)

                # Filter out system/subtype messages, tag with channel info.
                # Bot messages are allowed through — the identity filter in
                # _handle_polled_messages handles self-loop prevention via
                # agent signatures, which also works for cross-project bots.
                for m in messages:
                    if m.get("subtype") is None:
                        m["_channel_name"] = channel_name
                        m["_channel_id"] = channel_id
                        all_messages.append(m)

            except urllib.error.HTTPError as e:
                if e.code == 429:
                    retry_after = int(e.headers.get("Retry-After", "30"))
                    print(f"[SLACK] Rate limited, backing off {retry_after}s")
                    time.sleep(retry_after)
                else:
                    print(f"[SLACK] HTTP error polling #{channel_name}: {e}")
            except Exception as e:
                print(f"[SLACK] Failed to poll #{channel_name}: {e}")

        self._save_last_read_all(updated_last_read)
        return all_messages

    # ── Background polling ───────────────────────────────────────────────────

    def start_background_polling(self) -> None:
        """Start a background thread that polls Slack for inbound messages.

        Polls every SLACK_POLL_INTERVAL_SECONDS (15s). Handles 429 rate
        limits with Retry-After backoff. A1: loads intake history from disk
        on startup.
        """
        if not self._enabled:
            return
        if self._poll_thread is not None and self._poll_thread.is_alive():
            return

        # A1: Load intake history from disk on startup
        self._load_intake_history()

        self._poll_stop_event.clear()

        def _poll_loop() -> None:
            while not self._poll_stop_event.is_set():
                try:
                    msgs = self.poll_messages()
                    if msgs:
                        print(f"[SLACK] Poll: {len(msgs)} message(s)")
                        self._handle_polled_messages(msgs)
                    if self._callbacks.check_suspensions:
                        self._callbacks.check_suspensions()
                except Exception as e:
                    print(f"[SLACK] Background poll error: {e}")
                self._poll_stop_event.wait(timeout=SLACK_POLL_INTERVAL_SECONDS)

        self._poll_thread = threading.Thread(
            target=_poll_loop, daemon=True, name="slack-poller"
        )
        self._poll_thread.start()
        print(f"[SLACK] Background polling started ({SLACK_POLL_INTERVAL_SECONDS}s interval)")

    def stop_background_polling(self) -> None:
        """Stop the background polling thread gracefully."""
        self._poll_stop_event.set()
        if self._poll_thread is not None:
            self._poll_thread.join(timeout=5)
            self._poll_thread = None

    # ── Message dedup pruning ────────────────────────────────────────────────

    def _prune_message_tracking(self) -> None:
        """Remove stale entries from processed/sent ts sets and self-reply window.

        Prunes _processed_message_ts and _own_sent_ts entries whose Slack ts
        (a Unix timestamp string) is older than MESSAGE_TRACKING_TTL_SECONDS.
        Prunes _self_reply_window entries outside LOOP_DETECTION_WINDOW_SECONDS.
        """
        cutoff_ts = time.time() - MESSAGE_TRACKING_TTL_SECONDS
        self._processed_message_ts = {
            ts
            for ts in self._processed_message_ts
            if _safe_float_ts(ts) > cutoff_ts
        }
        self._own_sent_ts = {
            ts for ts in self._own_sent_ts if _safe_float_ts(ts) > cutoff_ts
        }
        now = time.monotonic()
        for channel_id in list(self._self_reply_window.keys()):
            self._self_reply_window[channel_id] = [
                t
                for t in self._self_reply_window[channel_id]
                if now - t <= LOOP_DETECTION_WINDOW_SECONDS
            ]
            if not self._self_reply_window[channel_id]:
                del self._self_reply_window[channel_id]

    # ── A1: Chain detection via on-disk intake history ───────────────────────

    def _load_intake_history(self) -> None:
        """Load intake history from disk, pruning stale entries."""
        try:
            with open(INTAKE_HISTORY_PATH, "r") as f:
                entries = json.load(f)
            if not isinstance(entries, list):
                entries = []
        except (IOError, json.JSONDecodeError):
            entries = []
        cutoff = time.time() - INTAKE_HISTORY_TTL_SECONDS
        self._intake_history = [
            e
            for e in entries
            if isinstance(e, dict) and e.get("timestamp", 0) > cutoff
        ]

    def _save_intake_history(self) -> None:
        """Persist intake history to disk."""
        try:
            os.makedirs(os.path.dirname(INTAKE_HISTORY_PATH), exist_ok=True)
            with open(INTAKE_HISTORY_PATH, "w") as f:
                json.dump(self._intake_history[-INTAKE_HISTORY_MAX_ENTRIES:], f)
        except IOError as e:
            print(f"[SLACK] Failed to save intake history: {e}")

    def _record_intake_history(self, item_number: int, slug: str, title_summary: str) -> None:
        """Append a new entry to the intake history after creating a backlog item.

        Args:
            item_number: Sequential backlog item number (e.g. 42).
            slug: URL-safe slug derived from the item title.
            title_summary: First 120 chars of the item title.
        """
        self._intake_history.append(
            {
                "item_number": item_number,
                "slug": slug,
                "title_summary": title_summary[:120],
                "timestamp": time.time(),
            }
        )
        if len(self._intake_history) > INTAKE_HISTORY_MAX_ENTRIES:
            self._intake_history = self._intake_history[-INTAKE_HISTORY_MAX_ENTRIES:]
        self._save_intake_history()

    def _is_chain_loop_artifact(self, text: str) -> bool:
        """Check if message text references a recently created backlog item.

        Detects the feedback loop: bot creates item #N, sends notification
        containing '#N', notification gets polled back and would create #N+1.

        Args:
            text: Slack message text to examine.

        Returns:
            True if the message appears to be a chain-loop artifact.
        """
        if not self._intake_history:
            self._load_intake_history()

        # Extract item number references like #17552
        refs = re.findall(r"#(\d+)", text)
        ref_numbers = {int(r) for r in refs}

        history_numbers = {
            e["item_number"]
            for e in self._intake_history
            if isinstance(e.get("item_number"), int)
        }
        if ref_numbers & history_numbers:
            return True

        # Check slug/filename patterns
        text_lower = text.lower()
        for entry in self._intake_history:
            slug = entry.get("slug", "")
            if slug and len(slug) > 8 and slug in text_lower:
                return True
        return False

    # ── A4: Global intake rate limiter ───────────────────────────────────────

    def _check_intake_rate_limit(self) -> bool:
        """Return True if the intake rate limit has been exceeded.

        Slides the window and checks against MAX_INTAKES_PER_WINDOW.
        Logs a loud warning when triggered.
        """
        now = time.time()
        cutoff = now - INTAKE_RATE_WINDOW_SECONDS
        self._intake_timestamps = [t for t in self._intake_timestamps if t > cutoff]
        if len(self._intake_timestamps) >= MAX_INTAKES_PER_WINDOW:
            print(
                f"[SLACK] WARNING: Intake rate limit exceeded! "
                f"{len(self._intake_timestamps)} intakes in "
                f"{INTAKE_RATE_WINDOW_SECONDS}s (max {MAX_INTAKES_PER_WINDOW}). "
                f"Refusing new intake."
            )
            return True
        return False

    def _record_intake_timestamp(self) -> None:
        """Record an intake event for rate limiting."""
        self._intake_timestamps.append(time.time())

    # ── Disk-persisted backlog creation throttle ─────────────────────────────

    def _load_backlog_throttle(self) -> dict[str, list[float]]:
        """Load the backlog creation throttle file from disk.

        Returns:
            Dict mapping item_type to list of unix timestamps.
        """
        try:
            with open(BACKLOG_CREATION_THROTTLE_PATH, "r") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except (FileNotFoundError, json.JSONDecodeError, IOError):
            pass
        return {}

    def _save_backlog_throttle(self, data: dict[str, list[float]]) -> None:
        """Persist the backlog creation throttle data to disk.

        Args:
            data: Dict mapping item_type to list of creation timestamps.
        """
        try:
            os.makedirs(
                os.path.dirname(BACKLOG_CREATION_THROTTLE_PATH), exist_ok=True
            )
            with open(BACKLOG_CREATION_THROTTLE_PATH, "w") as f:
                json.dump(data, f)
        except IOError as e:
            print(f"[SLACK] Failed to save backlog throttle: {e}")

    def _check_backlog_throttle(self, item_type: str) -> bool:
        """Return True if backlog creation should be blocked for item_type.

        Loads the disk-persisted throttle file, prunes entries older than
        BACKLOG_THROTTLE_WINDOW_SECONDS, and checks against the per-type limit.

        Args:
            item_type: 'feature' or 'defect'.
        """
        max_per_window = (
            MAX_DEFECTS_PER_HOUR if item_type == "defect" else MAX_FEATURES_PER_HOUR
        )
        data = self._load_backlog_throttle()
        now = time.time()
        cutoff = now - BACKLOG_THROTTLE_WINDOW_SECONDS

        entries = data.get(item_type, [])
        entries = [ts for ts in entries if isinstance(ts, (int, float)) and ts > cutoff]
        data[item_type] = entries
        self._save_backlog_throttle(data)

        if len(entries) >= max_per_window:
            print(
                f"[SLACK] WARNING: Backlog creation throttle triggered! "
                f"{len(entries)} {item_type}s created in the last "
                f"{BACKLOG_THROTTLE_WINDOW_SECONDS}s (max {max_per_window}). "
                f"Refusing new {item_type}."
            )
            return True
        return False

    def _record_backlog_creation(self, item_type: str) -> None:
        """Record a backlog creation event in the disk-persisted throttle.

        Args:
            item_type: 'feature' or 'defect'.
        """
        data = self._load_backlog_throttle()
        entries = data.get(item_type, [])
        entries.append(time.time())
        data[item_type] = entries
        self._save_backlog_throttle(data)

    # ── Backlog item creation ────────────────────────────────────────────────

    def create_backlog_item(
        self,
        item_type: str,
        title: str,
        body: str,
        user: str = "",
        ts: str = "",
    ) -> dict[str, str | int]:
        """Create a backlog markdown file from a Slack message.

        Checks disk-persisted throttle before writing. Records the creation
        in A1 intake history and the throttle on success.

        Args:
            item_type: 'feature' or 'defect'.
            title: Item title.
            body: Item description.
            user: Slack user ID who sent the message.
            ts: Message timestamp.

        Returns:
            Dict with keys filepath, filename, item_number on success,
            or empty dict on error or throttle block.
        """
        if item_type not in ("feature", "defect"):
            return {}

        if self._check_backlog_throttle(item_type):
            return {}

        backlog_dir = (
            "docs/feature-backlog" if item_type == "feature" else "docs/defect-backlog"
        )

        try:
            existing = [
                f for f in os.listdir(backlog_dir) if f.endswith(".md") and f[0].isdigit()
            ]
            numbers: list[int] = []
            for f in existing:
                parts = f.split("-", 1)
                if parts[0].isdigit():
                    numbers.append(int(parts[0]))
            next_num = max(numbers) + 1 if numbers else 1
        except (OSError, ValueError):
            next_num = 1

        # Build a URL-safe slug from the title
        slug = title.lower().strip().replace(" ", "-")
        slug = "".join(c for c in slug if c.isalnum() or c == "-")
        slug = slug.strip("-") or "untitled"

        filename = f"{next_num:02d}-{slug}.md"
        filepath = os.path.join(backlog_dir, filename)

        source_line = "Created from Slack message"
        if user:
            source_line += f" by {user}"
        if ts:
            source_line += f" at {ts}"
        source_line += "."

        content = (
            f"# {title}\n\n"
            f"## Status: Open\n\n"
            f"## Priority: Medium\n\n"
            f"## Summary\n\n"
            f"{body if body else title}\n\n"
            f"## Source\n\n"
            f"{source_line}\n"
        )

        try:
            os.makedirs(backlog_dir, exist_ok=True)
            with open(filepath, "w") as f:
                f.write(content)
            self._record_intake_history(next_num, slug, title[:120])
            self._record_backlog_creation(item_type)
            return {"filepath": filepath, "filename": filename, "item_number": next_num}
        except IOError as e:
            print(f"[SLACK] Failed to create backlog item: {e}")
            return {}

    # ── LLM routing ──────────────────────────────────────────────────────────

    def _route_message_via_llm(self, text: str) -> dict[str, str]:
        """Classify a Slack message using an LLM call.

        Sends the message text to a fast model to determine the appropriate
        pipeline action instead of using brittle keyword matching.

        Args:
            text: The Slack message text to classify.

        Returns:
            Dict with at minimum an "action" key. Possible actions:
            stop_pipeline, skip_item, get_status, create_feature,
            create_defect, ask_question, none.
        """
        fallback: dict[str, str] = {"action": "none"}
        if not text or not text.strip():
            return fallback
        if not self._callbacks.call_claude:
            return fallback

        prompt = MESSAGE_ROUTING_PROMPT.format(text=text)
        try:
            response = self._callbacks.call_claude(
                prompt, "haiku", MESSAGE_ROUTING_TIMEOUT_SECONDS
            )
            if not response:
                return fallback
            result = _extract_json(response)
            if isinstance(result, dict) and "action" in result:
                return result
            logger.debug("LLM routing returned non-actionable response: %s", response[:200])
            return fallback
        except Exception as e:
            logger.warning("LLM routing failed: %s", e)
            return fallback

    # ── Action execution ─────────────────────────────────────────────────────

    def _execute_routed_action(
        self, routing: dict, user: str, ts: str, channel_id: str
    ) -> None:
        """Execute the action determined by LLM message routing.

        Maps LLM routing decisions to the appropriate callback.

        Args:
            routing: Dict from _route_message_via_llm with "action" key.
            user: Slack user ID.
            ts: Message timestamp.
            channel_id: Channel to reply in.
        """
        action = routing.get("action", "none")

        if action == "stop_pipeline":
            self.handle_control_command(
                routing.get("title", "stop"),
                "control_stop",
                channel_id=channel_id,
            )

        elif action == "skip_item":
            self.handle_control_command("skip", "control_skip", channel_id=channel_id)

        elif action == "get_status":
            if self._callbacks.answer_question:
                threading.Thread(
                    target=self._callbacks.answer_question,
                    args=("status",),
                    kwargs={"channel_id": channel_id},
                    daemon=True,
                ).start()

        elif action in ("create_feature", "create_defect"):
            item_type = "feature" if action == "create_feature" else "defect"
            title = routing.get("title", f"Untitled {item_type}")
            body = routing.get("body", "")
            intake = IntakeState(
                channel_id=channel_id,
                channel_name="",
                original_text=f"{title}\n{body}".strip(),
                user=user,
                ts=ts,
                item_type=item_type,
            )
            intake_key = f"routed:{ts}"
            if self._callbacks.intake_lock is not None and self._callbacks.pending_intakes is not None:
                with self._callbacks.intake_lock:
                    self._callbacks.pending_intakes[intake_key] = intake
            if self._callbacks.run_intake:
                threading.Thread(
                    target=self._callbacks.run_intake,
                    args=(intake,),
                    daemon=True,
                ).start()

        elif action == "ask_question":
            question = routing.get("question", "")
            if question and self._callbacks.answer_question:
                threading.Thread(
                    target=self._callbacks.answer_question,
                    args=(question,),
                    kwargs={"channel_id": channel_id},
                    daemon=True,
                ).start()

        else:
            print(f"[SLACK] No action for routed message (action={action})")

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
        if classification == "control_stop":
            print(f"[SLACK] STOP command received from channel {channel_id}: {command!r}")
            try:
                with open(STOP_SEMAPHORE_PATH, "w") as f:
                    f.write(f"stop requested via Slack: {command}\n")
                if self._callbacks.send_status:
                    self._callbacks.send_status(
                        "*Stop requested* via Slack. Pipeline will stop after current task.",
                        "warning",
                        channel_id,
                    )
            except IOError as e:
                print(f"[SLACK] Failed to write stop semaphore: {e}")

        elif classification == "control_skip":
            if self._callbacks.send_status:
                self._callbacks.send_status(
                    "*Skip requested* via Slack. (Note: skip is not yet implemented "
                    "in the orchestrator. Use 'stop' to halt the pipeline.)",
                    "warning",
                    channel_id,
                )

        elif classification == "info_request":
            if self._callbacks.answer_question:
                self._callbacks.answer_question("status", channel_id=channel_id)

    # ── Message handling ─────────────────────────────────────────────────────

    def _handle_polled_messages(self, messages: list[dict]) -> None:
        """Route polled Slack messages to the appropriate handlers.

        Applies safety filters A1-A4 and addressing rules before dispatching
        to channel-role-based or LLM-based routing.

        Args:
            messages: List of Slack message dicts (tagged with _channel_name/_channel_id).
        """
        for msg in messages:
            text = msg.get("text", "").strip()
            if not text:
                continue

            ts = msg.get("ts", "")
            channel_id_key = msg.get("_channel_id", "")
            ch_log = msg.get("_channel_name", "?")
            preview = text[:60]
            is_self_origin = bool(ts and ts in self._own_sent_ts)

            # Dedup: skip already-processed messages
            if ts and ts in self._processed_message_ts:
                print(f"[SLACK] Filter: skip already-processed ts={ts}")
                continue

            # A3: Content-based notification pattern filter
            if BOT_NOTIFICATION_PATTERN.search(text):
                print(f"[SLACK] Filter: skip bot-notification-pattern #{ch_log}: {preview!r}")
                if ts:
                    self._processed_message_ts.add(ts)
                continue

            # A1: Chain detection — skip messages referencing recently created
            # backlog items (feedback loop artifacts)
            if self._is_chain_loop_artifact(text):
                print(f"[SLACK] Filter: skip chain-loop-artifact #{ch_log}: {preview!r}")
                if ts:
                    self._processed_message_ts.add(ts)
                continue

            # A2: Self-origin + loop detection
            if is_self_origin:
                now = time.monotonic()
                window = self._self_reply_window.get(channel_id_key, [])
                recent_count = sum(
                    1 for t in window if now - t <= LOOP_DETECTION_WINDOW_SECONDS
                )
                if recent_count >= MAX_SELF_REPLIES_PER_WINDOW:
                    print(f"[SLACK] Filter: skip loop-detected #{ch_log}: {preview!r}")
                    continue
                print(f"[SLACK] Filter: accept self-origin #{ch_log}: {preview!r}")

            # Addressing rules: check @AgentName mentions
            if self._agent_identity:
                addresses = set(AGENT_ADDRESS_PATTERN.findall(text))
                our_names = self._agent_identity.all_names()
                if addresses:
                    addressed_to_us = bool(addresses & our_names)
                    addressed_to_others = bool(addresses - our_names)
                    # Rule 2: Addressed only to others, not us → skip
                    if addressed_to_others and not addressed_to_us:
                        print(
                            f"[SLACK] Filter: skip addressed-to-other "
                            f"addrs={addresses} #{ch_log}: {preview!r}"
                        )
                        continue
                    # Rule 3: Addressed to us → fall through to process
                    print(
                        f"[SLACK] Filter: accept addressed-to-us "
                        f"addrs={addresses & our_names} #{ch_log}: {preview!r}"
                    )
                else:
                    # Rule 4: No addresses (broadcast) → fall through to process
                    print(f"[SLACK] Filter: accept broadcast #{ch_log}: {preview!r}")

            user = msg.get("user", "unknown")
            channel_name = msg.get("_channel_name", "")
            reply_to = channel_id_key
            channel_role = self._get_channel_role(channel_name)

            # Channel-based routing: channel suffix determines item type
            if channel_role in ("feature", "defect"):
                if len(text) < MINIMUM_INTAKE_MESSAGE_LENGTH:
                    print(
                        f"[SLACK] {channel_role.title()} rejected (too short, "
                        f"{len(text)} chars): {text!r}"
                    )
                    if self._callbacks.build_block and self._callbacks.post_message:
                        try:
                            payload = self._callbacks.build_block(
                                INTAKE_CLARIFICATION_TEMPLATE, "warning"
                            )
                            if ts:
                                payload["thread_ts"] = ts
                            self._callbacks.post_message(payload, reply_to)
                        except Exception:
                            pass
                    if ts:
                        self._processed_message_ts.add(ts)
                    continue

                intake_key = f"{channel_name}:{ts}"
                print(
                    f"[SLACK] {channel_role.title()} request from "
                    f"#{channel_name}: {text[:80]}"
                )
                intake = IntakeState(
                    channel_id=reply_to,
                    channel_name=channel_name,
                    original_text=text,
                    user=user,
                    ts=ts,
                    item_type=channel_role,
                )
                if self._callbacks.intake_lock is not None and self._callbacks.pending_intakes is not None:
                    with self._callbacks.intake_lock:
                        self._callbacks.pending_intakes[intake_key] = intake
                if self._callbacks.run_intake:
                    threading.Thread(
                        target=self._callbacks.run_intake,
                        args=(intake,),
                        daemon=True,
                    ).start()

            elif channel_role == "question":
                print(f"[SLACK] Question from #{channel_name}: {text[:80]}")
                if self._callbacks.answer_question:
                    threading.Thread(
                        target=self._callbacks.answer_question,
                        args=(text,),
                        kwargs={"channel_id": reply_to},
                        daemon=True,
                    ).start()

            else:
                # control channel or unrecognised: use LLM routing
                routing = self._route_message_via_llm(text)
                self._execute_routed_action(routing, user, ts, reply_to)

            # Track ts after routing to prevent duplicate processing
            if ts:
                self._processed_message_ts.add(ts)
                if is_self_origin:
                    window = self._self_reply_window.setdefault(reply_to, [])
                    window.append(time.monotonic())
