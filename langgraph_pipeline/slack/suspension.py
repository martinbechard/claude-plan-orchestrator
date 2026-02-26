# langgraph_pipeline/slack/suspension.py
# Human-in-the-loop question/answer flows, 5-Whys intake analysis, IntakeState.
# Design: docs/plans/2026-02-26-03-extract-slack-modules-design.md

"""IntakeState dataclass and suspension/intake flow logic.

Extracted from plan-orchestrator.py SlackNotifier class:
send_question, post_suspension_question, check_suspension_reply,
_check_all_suspensions, answer_question, _answer_question_inner,
_run_intake_analysis, _run_intake_analysis_inner, _parse_intake_response.
IntakeState dataclass (plan-orchestrator.py line 1291).

Task 2.2 fills in the full implementation. This stub provides IntakeState
for import by poller.py (task 2.1).
"""

from dataclasses import dataclass, field


# ── IntakeState dataclass ────────────────────────────────────────────────────


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
