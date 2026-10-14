"""Fakes for the evidence tests: a runner labelled like the real simulator, a priced LLM and
an app state wired to them. No Docker, no live model calls."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar

import pytest

from api.adapters.llm import Budget, FakeLLM, LLMReply
from api.adapters.sandbox import FakeRunner, ProgressFn, SimJob, failed_result
from api.app.state import build_state
from api.core.settings import Settings
from api.models import RunResult
from api.orchestrator.session import SessionManager
from api.tests.test_redteam import BLUE, red_reply

Outcome = Callable[[SimJob], str | None]


class SimLikeRunner(FakeRunner):
    """FakeRunner labelled like the real simulator, so the evidence rules can be exercised
    without Docker. `outcome(job)` may return "timeout", "failed" or "partial" for a run;
    every other run ends normally with everyone out."""

    provider = "docker"

    def __init__(self, runs_dir: Path, outcome: Outcome | None = None) -> None:
        super().__init__(runs_dir)
        self.outcome: Outcome = outcome or (lambda job: None)

    async def run(self, job: SimJob, on_progress: ProgressFn | None = None) -> RunResult:
        res = await super().run(job, on_progress)
        what = self.outcome(job)
        if what in ("timeout", "failed"):
            return failed_result(job, self.provider, "Injected (test)", status=what, runtime=30.0)
        res.engine, res.provider, res.runtime_s = "jupedsim", self.provider, 2.5
        res.metrics.extra.pop("rset_extrapolated_s", None)
        if what == "partial":
            res.status = "partial"
            res.metrics.agents_not_evacuated = 7
        else:
            res.status = "ok"
            res.metrics.agents_not_evacuated = 0
        return res


class PricedLLM(FakeLLM):
    """FakeLLM that bills like a hosted model, so the cost record has charges to add up."""

    USD_PER_CALL: ClassVar[dict[str, float]] = {
        "fast": 0.0002,
        "main": 0.0005,
        "long": 0.0007,
        "judge": 0.0011,
    }

    async def chat(  # type: ignore[override]
        self, role: Any, messages: list[dict[str, str]], schema: Any = None, **kw: Any
    ) -> LLMReply:
        budget: Budget | None = kw.pop("budget", None)
        if budget is not None:
            budget.check()
        reply = await super().chat(role, messages, schema, **kw)
        reply.usage = reply.usage.model_copy(
            update={
                "provider": "openrouter",
                "model": f"vendor/model-{role}",
                "cost_usd": self.USD_PER_CALL.get(str(role), 0.0003),
            }
        )
        if budget is not None:
            budget.add(reply.usage)
        return reply


def is_after(job: SimJob) -> bool:
    """The confirmation run of the fixed plan (tier 3, parent node "final:before")."""
    return job.request.tier == 3 and job.request.parent_run_id == "final:before"


def is_before(job: SimJob) -> bool:
    """The confirmation run of the original plan under the worst attack."""
    return job.request.tier == 3 and job.request.attack_id is not None and not is_after(job)


def use_test_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Settings for an isolated database and run folder under `tmp_path`."""
    settings = Settings(
        _env_file=None,
        db_url=f"sqlite:///{tmp_path / 's.sqlite'}",
        runs_dir=tmp_path / "runs",
        cache_dir=tmp_path / "c",
        llm_provider="fake",
        sandbox_provider="fake",
        offline=True,
        target_evac_indoor_s=120,
        fix_min_gain=0.01,  # the scripted east door helps by about 5%: keep it
    )
    monkeypatch.setattr("api.core.settings.get_settings", lambda: settings)
    monkeypatch.setattr("api.db.session.get_settings", lambda: settings)
    monkeypatch.setattr("api.orchestrator.demos.DEMO_DIR", tmp_path / "no-demos")
    reset_engine()
    return settings


def reset_engine() -> None:
    from api.db import session as dbs

    dbs.get_engine.cache_clear()


def app_state(
    settings: Settings,
    outcome: Outcome | None = None,
    llm_cls: type[FakeLLM] = FakeLLM,
    fake: bool = False,
) -> Any:
    """App state with scripted agents and a simulator-like (or the plain fake) runner."""
    script: dict[str, Any] = {
        "red_team": red_reply,
        "blue_team": BLUE,
        "judge": {"summary": "The plan was tested.", "recommendations": []},
    }
    runner = FakeRunner(settings.runs_dir) if fake else SimLikeRunner(settings.runs_dir, outcome)
    st = build_state(settings, llm=llm_cls(script, settings), runner=runner)
    st.sessions = SessionManager(st)
    return st
