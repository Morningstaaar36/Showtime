"""Typed simulation evidence (P2-03): what kind of evidence each run result is."""

from __future__ import annotations

import pytest

from api.models import RunResult, result_basis


def _r(**kw: object) -> RunResult:
    return RunResult.model_validate({"run_id": "r_x", "tier": 3, "status": "ok", **kw})


@pytest.mark.parametrize(
    ("kw", "basis"),
    [
        ({"tier": 1}, "instant_estimate"),
        ({"tier": 1, "status": "partial"}, "instant_estimate"),
        ({"tier": 3}, "completed_simulation"),
        ({"tier": 2}, "completed_simulation"),  # a quick run that ended normally
        ({"tier": 2, "status": "partial"}, "partial_simulation"),
        ({"tier": 3, "status": "partial"}, "partial_simulation"),
        ({"engine": "fake", "provider": "fake"}, "preview"),
        ({"provider": "fake"}, "preview"),
        ({"engine": ""}, "unknown"),
        ({"status": "failed"}, "unknown"),
        ({"status": "timeout"}, "unknown"),
        ({"status": "cancelled"}, "unknown"),
        ({"status": "queued"}, "unknown"),
        ({"status": "running"}, "unknown"),
        ({"tier": 1, "status": "failed"}, "unknown"),
    ],
)
def test_result_basis_semantics(kw: dict[str, object], basis: str) -> None:
    r = _r(**kw)
    assert result_basis(r) == basis
    assert r.basis == basis


def test_basis_is_serialized_and_never_goes_stale() -> None:
    r = _r(tier=1)
    assert r.model_dump()["basis"] == "instant_estimate"
    # a copy that becomes a simulation result (as the mock sandbox does) is re-derived
    sim = r.model_copy(deep=True)
    sim.tier = 3
    sim.engine, sim.provider = "fake", "fake"
    assert sim.basis == "preview"
    sim.engine, sim.provider, sim.status = "jupedsim", "docker", "timeout"
    assert sim.basis == "unknown"


def test_stored_results_load_with_or_without_basis() -> None:
    old = {"run_id": "r_old", "tier": 3, "status": "partial", "engine": "jupedsim"}
    assert RunResult.model_validate(old).basis == "partial_simulation"
    # a newer stored copy carries the derived field: it is ignored and re-derived
    new = {**old, "status": "ok", "basis": "unknown"}
    assert RunResult.model_validate(new).basis == "completed_simulation"
    # JSON round trip
    r = _r(tier=2, status="partial")
    assert RunResult.model_validate_json(r.model_dump_json()).basis == "partial_simulation"
