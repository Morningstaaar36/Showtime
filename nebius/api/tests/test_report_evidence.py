"""Reports must distinguish previews, unsuccessful runs, and measurements."""

import pytest

from api.models import RunResult
from plugins.export_html_report import source_label, verdict


@pytest.mark.parametrize(
    "status", ["failed", "timeout", "cancelled", "queued", "running", "partial"]
)
def test_incomplete_reports_never_claim_a_passing_plan(status: str) -> None:
    result = RunResult(run_id="r_test", tier=3, status=status)
    assert verdict(result, 5)[0] != "Holds"
    assert "confirmed by simulation" not in source_label(result)


def test_fake_report_is_not_a_simulation() -> None:
    result = RunResult(run_id="r_preview", tier=3, status="ok", engine="fake", provider="fake")
    assert verdict(result, 5) == ("Preview only — not simulated", "neutral")
    assert source_label(result) == "preview only (no simulation)"
