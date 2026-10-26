"""The sandbox feed: every run's state, time, limits and, for an AI-written script, what
happened to it (ran, refused, stopped) with the exact reason. Structured: never container output."""

from __future__ import annotations

from typing import Any

from api.adapters.sandbox import SimJob
from api.core.templates import get_template
from api.models import RunRequest, RunResult
from api.orchestrator.runs import sandbox_outcome
from api.tests.test_redteam import _run_session, state  # noqa: F401

SCRIPT = [{"type": "script", "title": "Smoke spreads", "code": "def on_step(v, a):\n    pass\n"}]


def _job(events: list[dict[str, Any]] | None = None) -> SimJob:
    v = get_template("school_wing")
    req = RunRequest(run_id="r_feed", venue_id=v.venue_id)
    return SimJob(request=req, venue=v, events=events or [], plan={}, sim_settings={})


def _res(status: str = "ok", notes: list[str] | None = None, error: str | None = None) -> RunResult:
    return RunResult(
        run_id="r_feed",
        tier=2,
        status=status,
        notes=notes or [],
        error=error,  # type: ignore[arg-type]
    )


def test_a_plain_run_that_finishes() -> None:
    assert sandbox_outcome(_res(), _job()) == {"state": "finished", "reason": None, "script": None}


def test_a_script_that_ran() -> None:
    out = sandbox_outcome(_res(), _job(SCRIPT))
    assert out["state"] == "finished" and out["script"] == {"state": "ran", "reason": None}


def test_a_script_refused_inside_the_sandbox() -> None:
    note = (
        "scenario script stopped: it failed the safety check "
        "(Line 1: import of 'socket' is not allowed (only math, statistics, random).)"
    )
    out = sandbox_outcome(_res(notes=[note]), _job(SCRIPT))
    assert out["state"] == "refused"
    assert out["script"]["state"] == "refused"
    assert out["script"]["reason"].startswith(
        "it failed the safety check (Line 1: import of 'socket'"
    )


def test_a_script_stopped_by_a_budget() -> None:
    note = (
        "scenario script stopped: it tried to use more memory than the sandbox allows (MemoryError)"
    )
    out = sandbox_outcome(_res(notes=[note]), _job(SCRIPT))
    assert out["state"] == "finished"
    assert out["script"] == {
        "state": "stopped",
        "reason": "it tried to use more memory than the sandbox allows (MemoryError)",
    }


def test_a_script_that_crashed_is_an_error_not_a_limit() -> None:
    # the AI's own bug (a crash), as the sandbox describes it: not one of the sandbox's limits
    for why in (
        "ValueError on line 5: max() iterable argument is empty",
        "ZeroDivisionError: division by zero",
    ):
        out = sandbox_outcome(_res(notes=[f"scenario script stopped: {why}"]), _job(SCRIPT))
        assert out["state"] == "finished"  # the crowd simulation itself still finished
        assert out["script"] == {"state": "error", "reason": why}
    for limit in ("one step ran more than 200,000 lines", "one step took longer than 50 ms"):
        out = sandbox_outcome(_res(notes=[f"scenario script stopped: {limit}"]), _job(SCRIPT))
        assert out["script"]["state"] == "stopped"


def test_a_run_past_its_time_or_memory_is_killed() -> None:
    late = sandbox_outcome(_res("timeout", error="Stopped after 240 s of wall-clock time."), _job())
    assert late == {
        "state": "killed",
        "reason": "Stopped after 240 s of wall-clock time.",
        "script": None,
    }
    oom = _res("failed", error="The simulation crashed (exit 137): out of memory")
    assert sandbox_outcome(oom, _job())["state"] == "killed"
    assert sandbox_outcome(_res("failed", error="boom"), _job())["state"] == "failed"


async def test_a_session_streams_each_runs_sandbox_lifecycle(state: Any) -> None:  # noqa: F811
    p = state.projects.create("Feed", template_id="school_wing")
    row = await _run_session(state, p.id, max_rounds=1, attacks_per_round=2)
    events = [e for e in state.sessions.stored_events(row.id) if e.type == "sandbox"]
    assert events, "no sandbox events"
    by_run: dict[str, list[str]] = {}
    for e in events:
        by_run.setdefault(e.payload["run_id"], []).append(e.payload["state"])
    for states in by_run.values():
        assert states[-1] in ("finished", "reused", "refused", "killed", "failed")
        if states[-1] != "reused":
            assert states[:2] == ["queued", "running"], states
    last = events[-1].payload
    assert last["limits"] and last["provider"] == "fake" and last["elapsed_s"] >= 0
    assert "label" in last and "stdout" not in last and "stderr" not in last


async def test_a_sandbox_that_stopped_and_was_restarted_says_so(state: Any) -> None:  # noqa: F811
    # the first container dies (killed from outside, or crashed); the run is retried once, and
    # the feed tells why instead of showing two "running" events and a clean finish
    from api.adapters.sandbox import failed_result

    real = state.runner.run
    first: list[str] = []

    async def flaky(job: SimJob, on_progress: Any = None) -> RunResult:
        if not first:
            first.append(job.request.run_id)
            return failed_result(job, "fake", "The simulation crashed (exit 137): killed")
        return await real(job, on_progress)

    state.runner.run = flaky
    p = state.projects.create("Retry", template_id="school_wing")
    row = await _run_session(state, p.id, max_rounds=1, attacks_per_round=1)
    events = [e.payload for e in state.sessions.stored_events(row.id) if e.type == "sandbox"]
    last = [e for e in events if e["run_id"] == first[0]][-1]
    assert last["state"] == "finished"
    assert last["retried"] == "The simulation crashed (exit 137): killed"
