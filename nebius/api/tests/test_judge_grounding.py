"""Numeric membership must not authorize unsupported outcome claims."""

from api.adapters.llm import FakeLLM
from api.agents.base import AgentEnv
from api.agents.judge import judge
from api.orchestrator.session import SessionManager


async def test_session_keeps_computed_outcomes_despite_valid_model_numbers() -> None:
    model = FakeLLM(
        {
            "judge": {
                "summary": "After fixes the plan was safe in 120 seconds.",
                "recommendations": ["Keep the existing exits clear."],
            }
        }
    )
    recorded = "No fixes were accepted. Planning aid, not a safety certification."
    text, recommendations, checked = await judge(
        AgentEnv(llm=model, audit=False),
        {"baseline_seconds": 120, "fixes_kept": []},
        recorded,
        computed_summary=True,
    )
    assert checked and recommendations == ["Keep the existing exits clear."]
    assert text == recorded and "After fixes" not in text


def test_unaccepted_candidate_metrics_do_not_become_an_improvement_claim() -> None:
    facts = {
        "venue": "Test hall",
        "people": 120,
        "scoreboard": [{"attacks": 1, "breaks": 1}],
        "worst_attack": "Blocked exit",
        "fixes_kept": [],
        "before_fixes": {"peak_density_ppm2": 5.2, "time_above_danger_s": 20},
        "after_fixes": {"peak_density_ppm2": 2.0, "time_above_danger_s": 0},
        "evidence_basis": "Preview only: these results use mock simulations.",
    }
    summary = SessionManager._template(facts)
    assert "No fixes were accepted." in summary
    assert "Preview only" in summary and "went from" not in summary
    assert summary.endswith("Planning aid, not a safety certification.")
