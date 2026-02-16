# tests/test_model_escalation.py
# Unit tests for EscalationConfig dataclass and model tier escalation logic.
# Design ref: docs/plans/2026-02-16-10-tiered-model-escalation-design.md

import importlib.util

# plan-orchestrator.py has a hyphen in the filename, so we must use importlib
# to load it as a module under a valid Python identifier.
spec = importlib.util.spec_from_file_location(
    "plan_orchestrator", "scripts/plan-orchestrator.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

EscalationConfig = mod.EscalationConfig
MODEL_TIERS = mod.MODEL_TIERS
parse_escalation_config = mod.parse_escalation_config


# --- EscalationConfig dataclass tests ---


def test_escalation_config_defaults():
    """Default EscalationConfig should be disabled with standard defaults."""
    cfg = EscalationConfig()
    assert cfg.enabled is False
    assert cfg.escalate_after == 2
    assert cfg.max_model == "opus"
    assert cfg.validation_model == "sonnet"
    assert cfg.starting_model == "sonnet"


def test_escalation_disabled_returns_agent_model():
    """When disabled, get_effective_model returns agent_model unchanged."""
    cfg = EscalationConfig(enabled=False)
    assert cfg.get_effective_model("haiku", 5) == "haiku"


def test_escalation_first_attempts_use_base_model():
    """Attempts within the escalate_after window use the base model."""
    cfg = EscalationConfig(enabled=True, escalate_after=2)
    assert cfg.get_effective_model("sonnet", 1) == "sonnet"
    assert cfg.get_effective_model("sonnet", 2) == "sonnet"


def test_escalation_after_failures():
    """Attempt beyond escalate_after promotes from sonnet to opus."""
    cfg = EscalationConfig(enabled=True, escalate_after=2)
    assert cfg.get_effective_model("sonnet", 3) == "opus"


def test_escalation_from_haiku_to_sonnet():
    """Haiku escalates to sonnet first, then to opus on further failures."""
    cfg = EscalationConfig(enabled=True, escalate_after=2)
    assert cfg.get_effective_model("haiku", 3) == "sonnet"
    assert cfg.get_effective_model("haiku", 5) == "opus"


def test_escalation_capped_at_max_model():
    """Escalation is capped at max_model even with many attempts."""
    cfg = EscalationConfig(enabled=True, escalate_after=1, max_model="sonnet")
    assert cfg.get_effective_model("haiku", 10) == "sonnet"


def test_escalation_already_at_max():
    """When already at max tier, escalation stays at that tier."""
    cfg = EscalationConfig(enabled=True, escalate_after=1, max_model="opus")
    assert cfg.get_effective_model("opus", 5) == "opus"


def test_escalation_unknown_model_passthrough():
    """Unknown models not in MODEL_TIERS are returned unchanged."""
    cfg = EscalationConfig(enabled=True)
    assert cfg.get_effective_model("custom-model", 5) == "custom-model"


def test_escalation_empty_model_uses_starting():
    """Empty agent_model falls back to starting_model and escalates normally."""
    cfg = EscalationConfig(enabled=True, starting_model="sonnet")
    assert cfg.get_effective_model("", 1) == "sonnet"
    assert cfg.get_effective_model("", 3) == "opus"


# --- parse_escalation_config tests ---


def test_parse_escalation_config_defaults():
    """Empty plan dict returns disabled EscalationConfig with all defaults."""
    cfg = parse_escalation_config({})
    assert cfg.enabled is False
    assert cfg.escalate_after == 2
    assert cfg.max_model == "opus"
    assert cfg.validation_model == "sonnet"
    assert cfg.starting_model == "sonnet"


def test_parse_escalation_config_enabled():
    """Plan with model_escalation block returns configured EscalationConfig."""
    plan = {
        "meta": {
            "model_escalation": {
                "enabled": True,
                "escalate_after": 3,
                "max_model": "sonnet",
            }
        }
    }
    cfg = parse_escalation_config(plan)
    assert cfg.enabled is True
    assert cfg.escalate_after == 3
    assert cfg.max_model == "sonnet"


def test_parse_escalation_config_partial():
    """Plan with only enabled=True uses defaults for remaining fields."""
    plan = {"meta": {"model_escalation": {"enabled": True}}}
    cfg = parse_escalation_config(plan)
    assert cfg.enabled is True
    assert cfg.escalate_after == 2
    assert cfg.max_model == "opus"
    assert cfg.validation_model == "sonnet"
    assert cfg.starting_model == "sonnet"


def test_parse_escalation_config_with_validation_model():
    """Plan with validation_model override propagates to config."""
    plan = {
        "meta": {
            "model_escalation": {
                "enabled": True,
                "validation_model": "haiku",
            }
        }
    }
    cfg = parse_escalation_config(plan)
    assert cfg.validation_model == "haiku"


def test_parse_escalation_config_no_meta():
    """Plan without meta key returns disabled config."""
    plan = {"sections": []}
    cfg = parse_escalation_config(plan)
    assert cfg.enabled is False
    assert cfg.escalate_after == 2
    assert cfg.max_model == "opus"
    assert cfg.validation_model == "sonnet"
    assert cfg.starting_model == "sonnet"
