# langgraph_pipeline/slack/identity.py
# Agent identity, signing, and self-message detection for shared Slack channels.
# Design: docs/plans/2026-02-26-03-extract-slack-modules-design.md

"""Agent identity constants, dataclass, factory, and signing mixin.

Extracted from plan-orchestrator.py (AgentIdentity at line 1559,
load_agent_identity at line 1586, and SlackNotifier identity methods).
"""

import contextlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ── Agent role constants ────────────────────────────────────────────────────

AGENT_ROLE_PIPELINE = "pipeline"
AGENT_ROLE_ORCHESTRATOR = "orchestrator"
AGENT_ROLE_INTAKE = "intake"
AGENT_ROLE_QA = "qa"

AGENT_ROLES = [AGENT_ROLE_PIPELINE, AGENT_ROLE_ORCHESTRATOR, AGENT_ROLE_INTAKE, AGENT_ROLE_QA]

# Regex: @AgentName, negative lookbehind avoids Slack native <@U...> mentions
AGENT_ADDRESS_PATTERN = re.compile(r"(?<![<])@([\w-]+)")

# Unicode em-dash used in agent signature: "— *AgentName*"
_SIGNATURE_SEPARATOR = "\u2014"


# ── AgentIdentity dataclass ─────────────────────────────────────────────────


@dataclass
class AgentIdentity:
    """Identity for agent messages in shared Slack channels.

    Each project chooses display names for its agents. Messages are signed
    with the active agent name, and inbound messages are filtered by address.
    """

    project: str
    agents: dict[str, str] = field(default_factory=dict)

    def name_for_role(self, role: str) -> str:
        """Return the display name for a given agent role.

        Falls back to '{Project}-{Role}' if the role is not explicitly mapped.
        """
        if role in self.agents:
            return self.agents[role]
        project_title = self.project.replace("-", " ").title().replace(" ", "-")
        return f"{project_title}-{role.title()}"

    def all_names(self) -> set[str]:
        """Return the set of all configured agent display names.

        Includes explicitly configured names and derived defaults for every
        role in AGENT_ROLES that is not explicitly mapped.
        """
        names = set(self.agents.values())
        for role in AGENT_ROLES:
            names.add(self.name_for_role(role))
        return names

    def is_own_signed_text(self, text: str) -> bool:
        """Return True if the text contains the signature of any agent in this identity.

        Used to detect inbound messages that were sent by this project's own
        agents (to avoid processing our own outputs as new inputs).

        Args:
            text: The Slack message text to examine.

        Returns:
            True if any of the identity's agent names appears as a signature.
        """
        for name in self.all_names():
            signature = f"{_SIGNATURE_SEPARATOR} *{name}*"
            if signature in text:
                return True
        return False


# ── Factory ─────────────────────────────────────────────────────────────────


def load_agent_identity(config: dict) -> AgentIdentity:
    """Load agent identity from the orchestrator config dict.

    Reads the optional 'identity' section. If absent, derives defaults
    from the current working directory basename.

    Args:
        config: The parsed orchestrator-config.yaml dict.

    Returns:
        An AgentIdentity populated from config or derived defaults.
    """
    identity_config = config.get("identity", {})
    if not isinstance(identity_config, dict):
        identity_config = {}

    project = identity_config.get("project", "")
    if not project:
        project = Path.cwd().name

    agents_map = identity_config.get("agents", {})
    if not isinstance(agents_map, dict):
        agents_map = {}

    return AgentIdentity(project=project, agents=agents_map)


# ── IdentityMixin ────────────────────────────────────────────────────────────


class IdentityMixin:
    """Mixin that adds agent identity and message-signing to a Slack class.

    Classes that inherit this mixin gain set_identity(), _as_role(), and
    _sign_text() without needing to duplicate the fields or logic.
    """

    def __init__(self) -> None:
        self._agent_identity: Optional[AgentIdentity] = None
        self._active_role: str = ""

    def set_identity(self, identity: AgentIdentity, role: str) -> None:
        """Configure agent identity and active role for message signing.

        Args:
            identity: The AgentIdentity for this project.
            role: The agent role constant (e.g., AGENT_ROLE_ORCHESTRATOR).
        """
        self._agent_identity = identity
        self._active_role = role

    def _as_role(self, role: str):
        """Context manager for temporary role switching.

        Saves the current role, switches to the given role for the duration
        of the block, and restores the original role on exit — even if an
        exception occurs.

        Args:
            role: The role to activate within the context block.
        """

        @contextlib.contextmanager
        def _switch():
            previous = self._active_role
            self._active_role = role
            try:
                yield
            finally:
                self._active_role = previous

        return _switch()

    def _sign_text(self, text: str) -> str:
        """Append agent signature to raw text if identity is configured.

        Args:
            text: The message text to sign.

        Returns:
            Text with ' — *AgentName*' appended, or unchanged if no identity.
        """
        if not self._agent_identity or not self._active_role:
            return text
        name = self._agent_identity.name_for_role(self._active_role)
        return f"{text} {_SIGNATURE_SEPARATOR} *{name}*"
