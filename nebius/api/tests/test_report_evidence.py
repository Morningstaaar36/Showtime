"""Reports must distinguish previews, unsuccessful runs, and measurements."""

import pytest

from api.core.extensions.breaks import BreakRule
from api.core.settings import Settings
from api.models import RunMetrics, RunResult
from plugins.export_html_report import source_label, verdict

RULE = BreakRule.of(Settings(_env_file=None), 300)


@pytest.mark.parametrize(
    "status", ["failed", "timeout", "cancelled", "queued", "running", "partial"]
)
def test_incomplete_reports_never_claim_a_passing_plan(status: str) -> None:
    result = RunResult(run_id="r_test", tier=3, status=status)
    assert verdict(result, RULE)[0] != "Holds"
    assert "confirmed by simulation" not in source_label(result)


def test_fake_report_is_not_a_simulation() -> None:
    result = RunResult(run_id="r_preview", tier=3, status="ok", engine="fake", provider="fake")
    assert verdict(result, RULE) == ("Preview only — not simulated", "neutral")
    assert source_label(result) == "preview only (no simulation)"


def test_the_report_judges_with_the_servers_rules() -> None:
    """A few people left inside: within the default tolerance, outside a strict one."""
    left = RunResult(
        run_id="r_t",
        tier=3,
        status="ok",
        engine="jupedsim",
        metrics=RunMetrics(evac_time_p95_s=60, agents_total=100, agents_not_evacuated=3),
    )
    assert verdict(left, RULE)[0] == "Test incomplete"  # not a failure, not a pass either
    strict = BreakRule.of(Settings(_env_file=None, stuck_tolerance_people=0), 300)
    assert verdict(left, strict)[0] == "Fails"
    assert verdict(left, None)[0] == "Not judged"
