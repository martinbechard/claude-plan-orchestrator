# langgraph_pipeline/executor/escalation.py
# Model escalation logic for the task execution subgraph.
# Design: docs/plans/2026-02-26-05-task-execution-subgraph-design.md

"""Model escalation for the executor subgraph.

Defines the ordered model tier progression (haiku -> sonnet -> opus) and
provides a function to advance the effective_model after a task failure.
Escalation is capped at opus; further failures do not change the model.
"""

from typing_extensions import TypedDict

from langgraph_pipeline.executor.state import ModelTier

# ─── Constants ────────────────────────────────────────────────────────────────

# Ordered progression from cheapest/fastest to most capable.
MODEL_TIER_PROGRESSION: tuple[ModelTier, ...] = ("haiku", "sonnet", "opus")

DEFAULT_STARTING_MODEL: ModelTier = "haiku"


# ─── Config schema ────────────────────────────────────────────────────────────


class EscalationConfig(TypedDict):
    """Configuration controlling when and how the model tier escalates.

    Attributes:
        enabled: Whether escalation is active for this plan.
        starting_model: Model tier used for the first attempt of each task.
    """

    enabled: bool
    starting_model: ModelTier


# ─── Public API ───────────────────────────────────────────────────────────────


def default_escalation_config() -> EscalationConfig:
    """Return a default EscalationConfig with escalation enabled at haiku.

    Returns:
        EscalationConfig starting at haiku with escalation enabled.
    """
    return EscalationConfig(enabled=True, starting_model=DEFAULT_STARTING_MODEL)


def escalate_model(current_model: ModelTier) -> ModelTier:
    """Advance to the next model tier after a task failure.

    If the current model is already at the highest tier (opus), it is returned
    unchanged — escalation is capped.

    Args:
        current_model: The model tier used in the failed attempt.

    Returns:
        The next model tier, or the same tier if already at opus.
    """
    current_index = MODEL_TIER_PROGRESSION.index(current_model)
    next_index = min(current_index + 1, len(MODEL_TIER_PROGRESSION) - 1)
    return MODEL_TIER_PROGRESSION[next_index]


def reset_model(config: EscalationConfig) -> ModelTier:
    """Reset the effective model to the configured starting tier after task success.

    Args:
        config: The EscalationConfig for the current plan.

    Returns:
        The starting model tier defined in the config.
    """
    return config["starting_model"]
