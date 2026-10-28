"""Typed evidence and the cost record of a session.

Execution status (did the session finish?) is separate from evaluation status (what do its
results show?). Unknown, partial, preview and estimate results never satisfy a full-simulation
gate. A simulation that failed or timed out is kept as it is (basis `unknown`); the instant
estimate shown in its place is a separate record linked to it by `extensions.fallback_for`.

`result_basis` is the one definition of a result's basis. It is defined with the RunResult
contract (so the computed `RunResult.basis` field can use it) and re-exported here.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Literal

from api.models import ResultBasis, RunResult, Usage, result_basis

__all__ = [
    "EVALUATION_LABELS",
    "FREE_PROVIDERS",
    "SIMULATION_BASES",
    "CostMeter",
    "EvaluationStatus",
    "attempt_basis",
    "attempt_id",
    "basis_phrase",
    "comparable",
    "describe_run",
    "evaluate",
    "evaluation_sentence",
    "evidence_sentence",
    "fallback_estimate",
    "fallback_for",
    "model_cost",
    "result_basis",
]

EvaluationStatus = Literal["confirmed", "partially_confirmed", "unconfirmed", "failed"]

SIMULATION_BASES: frozenset[ResultBasis] = frozenset({"partial_simulation", "completed_simulation"})
"""Results from the real simulator (time-capped or complete)."""

FREE_PROVIDERS = frozenset({"local", "local-fallback", "fake"})
"""Model providers that never charge for inference."""

EVALUATION_LABELS: dict[str, str] = {
    "confirmed": "confirmed by full simulations",
    "partially_confirmed": "partly confirmed",
    "unconfirmed": "not confirmed",
    "failed": "confirmation failed",
}


# --------------------------------------------------------------------------- result bases


def fallback_for(r: RunResult) -> str | None:
    """Id of the failed simulation this instant estimate stands in for (None otherwise)."""
    v = r.extensions.get("fallback_for")
    return str(v) if v else None


def attempt_basis(r: RunResult) -> ResultBasis:
    """Basis of the simulation that was attempted. An estimate shown in place of a failed
    simulation stands for a run that did not finish, so its attempt is `unknown`."""
    return "unknown" if fallback_for(r) else r.basis


def attempt_id(r: RunResult) -> str:
    """Run id of the simulation that was attempted (the failed run for a fallback)."""
    return fallback_for(r) or r.run_id


def basis_phrase(basis: ResultBasis, tier: int = 3) -> str:
    """Plain words for a result basis, used in generated text."""
    if basis == "completed_simulation":
        return "full simulation" if tier == 3 else "quick simulation that ran to the end"
    if basis == "partial_simulation":
        return (
            "quick simulation (first minutes only)"
            if tier == 2
            else "full simulation that stopped before everyone was out"
        )
    if basis == "instant_estimate":
        return "instant estimate"
    if basis == "preview":
        return "preview from the mock sandbox (not a simulation)"
    return "simulation that did not finish"


def describe_run(r: RunResult) -> str:
    """What a result is, with its run id (for sources and footnotes)."""
    failed = fallback_for(r)
    if failed:
        return (
            f"instant estimate, run {r.run_id}, shown because simulation run {failed} "
            "did not finish"
        )
    return f"{basis_phrase(r.basis, r.tier)}, run {r.run_id}"


def evidence_sentence(run: RunResult | None) -> str:
    """One sentence on what the headline result is based on (for summaries and the judge)."""
    if run is None:
        return "No usable result was available."
    if fallback_for(run):
        return (
            "The simulation for these results did not finish; instant estimates are shown "
            "in its place."
        )
    basis = run.basis
    if basis == "preview":
        return "Preview only: these results use mock simulations."
    if basis == "instant_estimate":
        return "These results are instant estimates."
    if basis == "unknown":
        if run.status in ("ok", "partial"):
            return "The simulation engine for these results is unverified."
        return "The simulation for these results did not finish."
    if basis == "partial_simulation":
        return "These results include an incomplete simulation."
    return "These results describe the tested scenarios under the configured assumptions."


def comparable(a: RunResult | None, b: RunResult | None) -> bool:
    """May `b` be compared with `a` to keep a change? Only when both are real simulations
    (complete or time-capped), or both are previews. An estimate standing in for a failed
    simulation, or a failed run, is never enough to keep a change."""
    if a is None or b is None:
        return False
    if a.basis in SIMULATION_BASES and b.basis in SIMULATION_BASES:
        return True
    return a.basis == b.basis == "preview"


def fallback_estimate(failed: RunResult, estimate: RunResult) -> RunResult:
    """A separate record, linked to the failed run, for the instant estimate shown in its
    place. The failed run itself is left unchanged."""
    fb = estimate.model_copy(deep=True)
    fb.run_id = f"{failed.run_id}-est"
    fb.parent_run_id = failed.parent_run_id
    fb.attack_id = failed.attack_id
    fb.fix_id = failed.fix_id
    fb.extensions = {
        **fb.extensions,
        "fallback_for": failed.run_id,
        "fallback_reason": failed.status,
    }
    fb.notes = [
        *fb.notes,
        f"The simulation (run {failed.run_id}) ended with status {failed.status}; "
        "this instant estimate is shown in its place.",
    ]
    return fb


# ----------------------------------------------------------------------------- evaluation


def _people_left(r: RunResult) -> str:
    n = r.metrics.agents_not_evacuated
    return f"{n:,} people were still inside when it stopped" if n else "it stopped early"


def _not_finished(label: str, r: RunResult) -> str:
    failed = fallback_for(r)
    if failed:
        return (
            f"The {label} simulation (run {failed}) did not finish "
            f"({r.extensions.get('fallback_reason', 'failed')}), so only an instant estimate "
            f"(run {r.run_id}) is available."
        )
    return f"The {label} simulation (run {r.run_id}) did not finish ({r.status})."


def evaluate(
    before: RunResult | None,
    after: RunResult | None,
    *,
    confirmation_ran: bool,
    kept: int,
    had_breaks: bool = True,
    stopped_reason: str = "",
    baseline: RunResult | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    """Evaluation status of a session's plan, separate from whether the session finished.

    `before`/`after` are the results used for the worst attack before and after the kept
    fixes (a fallback estimate stands for its failed simulation). `confirmed` only when both
    confirmation runs are full simulations that ran to the end; every other outcome says why
    it is less than that. `*_basis` and `*_run_id` describe the simulations attempted;
    `fallback_run_ids` names the estimates shown in place of the ones that did not finish.
    """
    reasons: list[str] = []
    status: EvaluationStatus
    bb = attempt_basis(before) if before is not None else None
    ab = attempt_basis(after) if after is not None else None
    if confirmation_ran:
        if before is None or after is None:
            status = "failed"
            reasons.append(
                "The confirmation runs could not be completed" + (f": {error}" if error else ".")
            )
        elif "unknown" in (bb, ab):
            status = "failed"
            reasons.extend(
                _not_finished(label, r)
                for label, r in (("before", before), ("after", after))
                if attempt_basis(r) == "unknown"
            )
        elif bb == ab == "completed_simulation":
            status = "confirmed"
            reasons.append(
                "The before and after full simulations of the worst attack both ran to the "
                "end, with no one left inside."
            )
        elif bb in SIMULATION_BASES and ab in SIMULATION_BASES:
            status = "partially_confirmed"
            reasons.extend(
                f"The {label} run is a {basis_phrase(r.basis, r.tier)}: {_people_left(r)}."
                for label, r in (("before", before), ("after", after))
                if r.basis == "partial_simulation"
            )
        elif "preview" in (bb, ab):
            status = "unconfirmed"
            reasons.append(
                "The before and after runs are previews from the mock sandbox, not simulations."
            )
        else:
            status = "unconfirmed"
            reasons.append("The before and after runs are not simulations.")
    else:
        status = "failed" if bb == "unknown" else "unconfirmed"
        if not had_breaks:
            reasons.append("No attack broke the plan, so there was nothing to fix or confirm.")
        elif kept == 0:
            reasons.append("No fixes were kept, so there was nothing to confirm.")
        elif error:
            reasons.append(f"The confirmation could not start ({error}).")
        elif stopped_reason.startswith(("stopped", "budget")):
            reasons.append(
                f"The session ended early ({stopped_reason}) before the kept fixes were confirmed."
            )
        elif stopped_reason.startswith("error"):
            reasons.append(
                "The session stopped with an error before the kept fixes were confirmed."
            )
        else:
            reasons.append("The kept fixes were not confirmed with full simulations.")
        if before is not None and bb == "unknown":
            label = "baseline" if before is baseline else "worst-attack"
            reasons.append(_not_finished(label, before))
    if baseline is not None and baseline is not before and attempt_basis(baseline) == "unknown":
        reasons.append(_not_finished("baseline", baseline))
    sides = (("baseline", baseline), ("before", before), ("after", after))
    return {
        "status": status,
        "before_basis": bb,
        "after_basis": ab,
        "reasons": reasons,
        "before_run_id": attempt_id(before) if before is not None else None,
        "after_run_id": attempt_id(after) if after is not None else None,
        "baseline_basis": attempt_basis(baseline) if baseline is not None else None,
        "fallback_run_ids": {
            side: r.run_id for side, r in sides if r is not None and fallback_for(r)
        },
    }


def evaluation_sentence(evaluation: dict[str, Any]) -> str:
    """The evaluation in plain sentences (for the computed summary)."""
    label = EVALUATION_LABELS.get(str(evaluation.get("status")), "not confirmed")
    reasons = " ".join(str(r) for r in evaluation.get("reasons", []))
    return f"Evaluation: {label}." + (f" {reasons}" if reasons else "")


# ---------------------------------------------------------------------------- cost record


def _bucket() -> dict[str, Any]:
    return {"calls": 0, "tokens_in": 0, "tokens_out": 0, "usd": 0.0}


def model_cost(u: Usage) -> float:
    """Inference charge of one call: free and local models, and cache replays, cost $0."""
    if u.cached or u.provider in FREE_PROVIDERS or u.model.endswith(":free"):
        return 0.0
    return float(u.cost_usd)


@dataclass
class CostMeter:
    """Measured cost of one session: model calls (the same usage records as the `agent_call`
    events) and simulations by kind (the same results as the `run_finished` events).

    A call and its one repair retry are reported together, as one call. Simulation seconds
    count fresh sandbox runs only; a reused (cached) run cost no new compute."""

    started: float = field(default_factory=time.monotonic)
    calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    usd: float = 0.0
    llm_cache_hits: int = 0
    by_role: dict[str, dict[str, Any]] = field(default_factory=dict)
    by_model: dict[str, dict[str, Any]] = field(default_factory=dict)
    instant_estimates: int = 0
    quick_sims: int = 0
    full_sims: int = 0
    failed_sims: int = 0
    sim_cache_hits: int = 0
    sim_seconds: float = 0.0

    def add_usage(self, u: Usage) -> None:
        """One model call."""
        usd = model_cost(u)
        self.calls += 1
        self.tokens_in += u.prompt_tokens
        self.tokens_out += u.completion_tokens
        self.usd += usd
        if u.cached:
            self.llm_cache_hits += 1
        for key, table in ((u.role, self.by_role), (u.model or "unknown", self.by_model)):
            b = table.setdefault(key, _bucket())
            b["calls"] += 1
            b["tokens_in"] += u.prompt_tokens
            b["tokens_out"] += u.completion_tokens
            b["usd"] += usd

    def add_estimates(self, n: int = 1) -> None:
        """Instant estimates used as evidence (screening, harm checks, fallbacks)."""
        self.instant_estimates += n

    def add_run(self, r: RunResult) -> None:
        """One simulation attempt, as returned by the run service (failed ones included)."""
        if r.tier == 1:
            return
        if r.tier == 2:
            self.quick_sims += 1
        else:
            self.full_sims += 1
        if r.basis == "unknown":
            self.failed_sims += 1
        if r.extensions.get("cache_hit"):
            self.sim_cache_hits += 1
        else:
            self.sim_seconds += r.runtime_s

    def record(self, wall_s: float | None = None) -> dict[str, Any]:
        """The cost record stored in the session summary."""

        def rounded(table: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
            return {k: {**v, "usd": round(float(v["usd"]), 6)} for k, v in table.items()}

        return {
            "usd_total": round(self.usd, 6),
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "calls": self.calls,
            "by_role": rounded(self.by_role),
            "by_model": rounded(self.by_model),
            "llm_cache_hits": self.llm_cache_hits,
            "sims": {
                "instant_estimates": self.instant_estimates,
                "quick_sims": self.quick_sims,
                "full_sims": self.full_sims,
                "failed": self.failed_sims,
                "cache_hits": self.sim_cache_hits,
                "sim_seconds": round(self.sim_seconds, 1),
            },
            "wall_s": round(wall_s if wall_s is not None else time.monotonic() - self.started, 1),
        }
