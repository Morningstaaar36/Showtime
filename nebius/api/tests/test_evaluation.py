"""Evaluation status and linked fallback records (P2-03): what a session's results show,
separate from whether the session finished. Pure functions, no simulator."""

from __future__ import annotations

from typing import Any

import pytest

from api.core.evidence import (
    attempt_basis,
    attempt_id,
    basis_phrase,
    comparable,
    describe_run,
    evaluate,
    evaluation_sentence,
    evidence_sentence,
    fallback_estimate,
    fallback_for,
)
from api.models import RunResult

BASES = ["instant_estimate", "partial_simulation", "completed_simulation", "preview", "unknown"]


def run(rid: str = "r_x", **kw: Any) -> RunResult:
    data: dict[str, Any] = {"run_id": rid, "tier": 3, "status": "ok", **kw}
    data.setdefault("metrics", {"agents_total": 100})
    return RunResult.model_validate(data)


def of_basis(basis: str, rid: str = "r_x") -> RunResult:
    """A tier-3 run with the given basis."""
    if basis == "instant_estimate":
        return run(rid, tier=1, engine="tier1", provider="local")
    if basis == "partial_simulation":
        return run(rid, status="partial", metrics={"agents_total": 100, "agents_not_evacuated": 12})
    if basis == "preview":
        return run(rid, engine="fake", provider="fake")
    if basis == "unknown":
        return run(rid, status="timeout")
    return run(rid)


def estimate_for(failed: RunResult) -> RunResult:
    est = run("r_t1", tier=1, engine="tier1", provider="local", metrics={"agents_total": 100})
    return fallback_estimate(failed, est)


def test_fallback_is_a_separate_linked_record() -> None:
    failed = run("r_after", status="timeout", parent_run_id="final:before", attack_id="A1")
    fb = estimate_for(failed)
    assert fb.run_id == "r_after-est" != failed.run_id
    assert fb.basis == "instant_estimate" and fb.tier == 1
    assert fb.extensions["fallback_for"] == "r_after"
    assert fb.extensions["fallback_reason"] == "timeout"
    assert (fb.parent_run_id, fb.attack_id) == ("final:before", "A1")
    assert "r_after" in fb.notes[-1]
    # the failed record is untouched and stays unknown
    assert failed.basis == "unknown" and failed.run_id == "r_after" and not failed.extensions
    # the estimate stands for a simulation that did not finish
    assert fallback_for(fb) == "r_after" and fallback_for(failed) is None
    assert attempt_basis(fb) == "unknown" and attempt_id(fb) == "r_after"
    assert attempt_basis(failed) == "unknown" and attempt_id(failed) == "r_after"


@pytest.mark.parametrize("before", BASES)
@pytest.mark.parametrize("after", BASES)
def test_confirmed_only_when_both_runs_completed(before: str, after: str) -> None:
    ev = evaluate(of_basis(before, "r_b"), of_basis(after, "r_a"), confirmation_ran=True, kept=1)
    confirmed = before == after == "completed_simulation"
    assert (ev["status"] == "confirmed") is confirmed
    assert (ev["before_basis"], ev["after_basis"]) == (before, after)
    assert ev["reasons"], "every evaluation says why"
    if "unknown" in (before, after):
        assert ev["status"] == "failed"


def test_timed_out_confirmation_with_fallback_is_failed_and_linked() -> None:
    before = of_basis("completed_simulation", "r_b")
    failed_after = run("r_a", status="timeout")
    shown = estimate_for(failed_after)
    ev = evaluate(before, shown, confirmation_ran=True, kept=1)
    assert ev["status"] == "failed"
    assert ev["after_basis"] == "unknown" and ev["after_run_id"] == "r_a"
    assert ev["fallback_run_ids"] == {"after": "r_a-est"}
    assert "did not finish (timeout)" in ev["reasons"][0]
    assert "r_a-est" in ev["reasons"][0]


def test_a_fallback_estimate_can_never_confirm() -> None:
    # even an estimate that "looks" perfect stands for a simulation that did not finish
    for side in ("before", "after"):
        good = of_basis("completed_simulation", "r_ok")
        fb = estimate_for(run("r_fail", status="failed"))
        pair = (fb, good) if side == "before" else (good, fb)
        ev = evaluate(*pair, confirmation_ran=True, kept=1)
        assert ev["status"] == "failed"
        assert ev[f"{side}_basis"] == "unknown"
        assert "confirmed" not in evaluation_sentence(ev).replace("confirmation failed", "")


def test_partial_confirmation_names_the_people_still_inside() -> None:
    ev = evaluate(
        of_basis("completed_simulation", "r_b"),
        of_basis("partial_simulation", "r_a"),
        confirmation_ran=True,
        kept=1,
    )
    assert ev["status"] == "partially_confirmed"
    assert ev["reasons"] == [
        "The after run is a full simulation that stopped before everyone was out: "
        "12 people were still inside when it stopped."
    ]


def test_confirmation_that_could_not_run_is_failed() -> None:
    ev = evaluate(
        of_basis("completed_simulation"),
        None,
        confirmation_ran=True,
        kept=1,
        error="budget: wall clock",
    )
    assert ev["status"] == "failed"
    assert ev["reasons"] == ["The confirmation runs could not be completed: budget: wall clock"]


@pytest.mark.parametrize(
    ("kw", "reason"),
    [
        ({"kept": 0, "had_breaks": False}, "No attack broke the plan"),
        ({"kept": 0}, "No fixes were kept"),
        ({"kept": 2, "stopped_reason": "budget: simulation runs"}, "ended early (budget"),
        ({"kept": 2, "stopped_reason": "stopped by user"}, "ended early (stopped by user)"),
        ({"kept": 2, "stopped_reason": "error: KeyError"}, "stopped with an error"),
        ({"kept": 2, "error": "budget: wall clock"}, "could not start (budget: wall clock)"),
        ({"kept": 2}, "not confirmed with full simulations"),
    ],
)
def test_without_confirmation_the_plan_is_unconfirmed(kw: dict[str, Any], reason: str) -> None:
    ev = evaluate(of_basis("partial_simulation"), None, confirmation_ran=False, **kw)
    assert ev["status"] == "unconfirmed"
    assert ev["after_basis"] is None and ev["after_run_id"] is None
    assert reason in ev["reasons"][0]


def test_unfinished_worst_attack_or_baseline_is_reported() -> None:
    worst = estimate_for(run("r_w", status="failed", tier=2))
    baseline = estimate_for(run("r_base", status="timeout"))
    ev = evaluate(worst, None, confirmation_ran=False, kept=0, baseline=baseline)
    assert ev["status"] == "failed"
    assert ev["baseline_basis"] == "unknown"
    assert ev["fallback_run_ids"] == {"baseline": "r_base-est", "before": "r_w-est"}
    assert any(r.startswith("The worst-attack simulation (run r_w)") for r in ev["reasons"])
    assert any(r.startswith("The baseline simulation (run r_base)") for r in ev["reasons"])
    # no attack at all: the baseline stands as "before" and is reported once
    ev = evaluate(baseline, None, confirmation_ran=False, kept=0, baseline=baseline)
    assert sum("baseline simulation" in r for r in ev["reasons"]) == 1


def test_comparisons_need_matching_evidence() -> None:
    sim, part = of_basis("completed_simulation"), of_basis("partial_simulation")
    prev, est = of_basis("preview"), estimate_for(run("r_f", status="timeout"))
    assert comparable(sim, part) and comparable(part, sim) and comparable(prev, prev)
    assert not comparable(sim, est) and not comparable(est, est)
    assert not comparable(sim, prev) and not comparable(sim, of_basis("unknown"))
    assert not comparable(sim, None) and not comparable(None, sim)


def test_wording_follows_the_basis() -> None:
    assert basis_phrase("completed_simulation", 3) == "full simulation"
    assert basis_phrase("completed_simulation", 2) == "quick simulation that ran to the end"
    assert basis_phrase("partial_simulation", 2) == "quick simulation (first minutes only)"
    assert basis_phrase("instant_estimate", 1) == "instant estimate"
    assert "not a simulation" in basis_phrase("preview", 3)
    assert basis_phrase("unknown", 3) == "simulation that did not finish"
    for b in BASES:
        assert "confirm" not in basis_phrase(b)  # type: ignore[arg-type]
    fb = estimate_for(run("r_a", status="timeout"))
    assert describe_run(fb) == (
        "instant estimate, run r_a-est, shown because simulation run r_a did not finish"
    )
    assert describe_run(of_basis("completed_simulation", "r_ok")) == "full simulation, run r_ok"
    assert evidence_sentence(fb).startswith("The simulation for these results did not finish")
    assert evidence_sentence(of_basis("unknown")) == (
        "The simulation for these results did not finish."
    )
    assert evidence_sentence(run(engine="")) == (
        "The simulation engine for these results is unverified."
    )
    assert evidence_sentence(of_basis("preview")).startswith("Preview only")
    assert evidence_sentence(None) == "No usable result was available."


def test_evaluation_sentence() -> None:
    done = of_basis("completed_simulation")
    ok = evaluate(done, done, confirmation_ran=True, kept=1)
    assert evaluation_sentence(ok).startswith("Evaluation: confirmed by full simulations.")
    none = evaluate(None, None, confirmation_ran=False, kept=0)
    assert evaluation_sentence(none) == (
        "Evaluation: not confirmed. No fixes were kept, so there was nothing to confirm."
    )
    assert evaluation_sentence({}) == "Evaluation: not confirmed."
