"""The cost record of a session (N16): model calls and simulations by kind, measured from
the session's own usage and run records. Pure accounting, no model or simulator calls."""

from __future__ import annotations

from typing import Any

import pytest

from api.core.evidence import CostMeter, model_cost
from api.models import RunResult, Usage


def usage(role: str = "main", **kw: Any) -> Usage:
    data: dict[str, Any] = {
        "role": role,
        "model": f"vendor/{role}",
        "prompt_tokens": 1000,
        "completion_tokens": 200,
        "cost_usd": 0.004,
        "provider": "openrouter",
        **kw,
    }
    return Usage.model_validate(data)


def sim(tier: int, status: str = "ok", runtime: float = 10.0, **ext: Any) -> RunResult:
    return RunResult(
        run_id=f"r_{tier}_{status}",
        tier=tier,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        runtime_s=runtime,
        extensions=ext,
    )


@pytest.mark.parametrize(
    "free",
    [
        {"provider": "local"},
        {"provider": "local-fallback"},
        {"provider": "fake"},
        {"model": "nvidia/nemotron-nano-9b-v2:free"},
        {"cached": True},
    ],
)
def test_free_local_and_cached_calls_cost_nothing(free: dict[str, Any]) -> None:
    assert model_cost(usage(**free)) == 0.0
    assert model_cost(usage()) == pytest.approx(0.004)


def test_model_calls_add_up_by_role_and_model() -> None:
    meter = CostMeter()
    meter.add_usage(usage("fast", cost_usd=0.001))
    meter.add_usage(usage("main"))
    meter.add_usage(usage("main", cached=True))
    meter.add_usage(usage("judge", provider="local", model="nemotron-local"))
    rec = meter.record(wall_s=12.34)
    assert rec["calls"] == 4
    assert (rec["tokens_in"], rec["tokens_out"]) == (4000, 800)
    assert rec["usd_total"] == pytest.approx(0.005)
    assert rec["llm_cache_hits"] == 1
    assert rec["by_role"]["main"] == {
        "calls": 2,
        "tokens_in": 2000,
        "tokens_out": 400,
        "usd": 0.004,
    }
    assert rec["by_model"]["nemotron-local"]["usd"] == 0.0
    assert set(rec["by_model"]) == {"vendor/fast", "vendor/main", "nemotron-local"}
    assert rec["wall_s"] == 12.3


def test_simulations_are_counted_by_kind() -> None:
    meter = CostMeter()
    meter.add_estimates(3)
    meter.add_run(sim(2))
    meter.add_run(sim(2, "partial", 20.0))
    meter.add_run(sim(3, "timeout", 240.0))  # failed attempts used compute too
    meter.add_run(sim(3, runtime=99.0, cache_hit=True))  # reused: no new compute
    meter.add_run(sim(1))  # instant estimates are counted with add_estimates
    sims = meter.record(wall_s=1.0)["sims"]
    assert sims == {
        "instant_estimates": 3,
        "quick_sims": 2,
        "full_sims": 2,
        "failed": 1,
        "cache_hits": 1,
        "sim_seconds": 270.0,
    }


def test_record_shape_is_stable() -> None:
    rec = CostMeter().record(wall_s=0.0)
    assert set(rec) == {
        "usd_total",
        "tokens_in",
        "tokens_out",
        "calls",
        "by_role",
        "by_model",
        "llm_cache_hits",
        "sims",
        "wall_s",
    }
    assert rec["usd_total"] == 0.0 and rec["calls"] == 0 and rec["by_role"] == {}
