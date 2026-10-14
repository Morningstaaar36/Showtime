"""Event Copilot and Autopilot as one LangGraph state graph.

Copilot: understand → (place named?) locate → (real site?) layout | design → estimate →
create → simulate → sweep → review.

Autopilot (N13) runs the same nodes, then tests the plan: simulate → (thorough) sweep →
red_team (a Red Team Night session: baseline, attacks, fixes, confirmation) → deliver (report
and cost record). An existing project enters at simulate. Fixes are tested, never applied: the
organizer accepts them on Your plan.

Each node streams progress through LangGraph's custom stream, and the graph's own structure is
served to the UI so it can be drawn as the agents work.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
from collections.abc import Callable, Iterable
from typing import Any, Protocol, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.types import StreamWriter

from api.agents.base import AgentEnv, AgentUnavailable
from api.agents.event_brief import read_brief
from api.agents.safety_officer import keep_checked, review_plan
from api.core.estimates import compute_estimates
from api.core.geometry import validate_venue
from api.core.site_layout import furnish
from api.db.models import UserSetting
from api.db.session import db_session
from api.models import Usage, Venue
from api.models.autopilot import STEP_LABELS, STEP_NODES, STEP_ORDER, STEP_PHASES, AutopilotCost
from api.models.venue_spec import EventBrief
from api.orchestrator import sweep, venue_sources
from api.orchestrator.copilot import _site_from_place, _step

log = logging.getLogger("showtime.copilot")


class CopilotState(TypedDict, total=False):
    """What flows between the nodes (JSON-serialisable so runs can be checkpointed)."""

    text: str
    brief: dict[str, Any]
    venue: dict[str, Any]
    real: bool
    notes: list[str]
    estimates: dict[str, Any]
    project_id: str
    run_id: str
    review: dict[str, Any]
    failed: str
    # Autopilot only
    autopilot: bool
    depth: str  # quick | thorough
    sweep_runs: list[str]
    session_id: str
    stopped: bool
    outage: bool
    result: dict[str, Any]


class AutopilotHooks(Protocol):
    """What the Autopilot driver (orchestrator/autopilot.py) lends the graph via its config."""

    session_config: dict[str, Any]

    def should_stop(self) -> bool:
        """The organizer pressed Stop."""
        ...

    def on_session(self, session_id: str) -> None:
        """The red-team session started (so Stop can reach it)."""
        ...

    def on_usage(self, usage: Usage) -> None:
        """Usage of one intake agent call (reading the request, designing the venue)."""
        ...

    def intake(self) -> dict[str, float]:
        """Intake usage so far: usd, tokens and calls."""
        ...


def _st(config: RunnableConfig) -> Any:
    return config["configurable"]["st"]


def _hooks(config: RunnableConfig) -> AutopilotHooks | None:
    hooks: AutopilotHooks | None = config["configurable"].get("autopilot")
    return hooks


def _meter(config: RunnableConfig) -> Callable[[Usage], None] | None:
    hooks = _hooks(config)
    return hooks.on_usage if hooks is not None else None


def _env(st: Any, extra: Callable[[Usage], None] | None = None) -> AgentEnv:
    if extra is None:
        return AgentEnv(llm=st.llm, project_id=None, on_usage=st.usage.add)

    def add(u: Usage) -> None:
        st.usage.add(u)
        extra(u)

    return AgentEnv(llm=st.llm, project_id=None, on_usage=add)


@dataclasses.dataclass
class _UsageTee:
    """The app's usage meter, also feeding an Autopilot run's own meter."""

    meter: Any
    extra: Callable[[Usage], None]

    def add(self, u: Usage) -> None:
        self.meter.add(u)
        self.extra(u)


def _metered(config: RunnableConfig) -> Any:
    """The app state, with agent usage also counted for this Autopilot run."""
    st, extra = _st(config), _meter(config)
    if extra is None:
        return st
    tee = _UsageTee(st.usage, extra)
    if not dataclasses.is_dataclass(st) or isinstance(st, type):
        return st
    return dataclasses.replace(st, usage=tee)


async def understand(state: CopilotState, config: RunnableConfig) -> CopilotState:
    """Brief agent: the request → event brief."""
    w = get_stream_writer()
    w(_step("brief", "running", "Reading your request", node="understand"))
    call = await read_brief(_env(_st(config), _meter(config)), state["text"])
    b = call.output
    if b is None:
        w(
            _step(
                "brief",
                "failed",
                "Could not read the request",
                "Say what the event is, where, when and for how many people.",
                node="understand",
            )
        )
        return {"failed": "brief"}
    parts = [
        b.place or "venue to design",
        b.start or "",
        f"{b.duration_h:g} h",
        "alcohol" if b.alcohol else "",
        b.audience,
    ]
    w(
        _step(
            "brief",
            "done",
            f"{b.title}: {b.kind} for {b.attendees:,} people",
            " · ".join(x for x in parts if x),
            node="understand",
            brief=b.model_dump(mode="json"),
        )
    )
    return {"brief": b.model_dump(mode="json"), "notes": list(b.assumptions)}


async def locate(state: CopilotState, config: RunnableConfig) -> CopilotState:
    """Find the named place and import the real site (OpenStreetMap)."""
    w = get_stream_writer()
    b = EventBrief.model_validate(state["brief"])
    w(_step("site", "running", f"Finding {b.place} on the map", node="locate"))
    draft, found = await _site_from_place(_st(config), b)
    if draft is None:
        w(_step("site", "warn", "Using a designed venue instead", found, node="locate"))
        return {"real": False}
    w(_step("site", "done", f"Imported the real site: {found}", node="locate"))
    return {
        "real": True,
        "venue": draft["venue"],
        "notes": [*state.get("notes", []), *draft.get("notes", [])],
    }


async def design(state: CopilotState, config: RunnableConfig) -> CopilotState:
    """Designer agent + solver: a venue from words."""
    w = get_stream_writer()
    b = EventBrief.model_validate(state["brief"])
    w(_step("site", "running", "Designing the venue from your description", node="design"))
    desc = b.layout or (
        f"{b.kind} venue for {b.attendees} {b.audience} people, {b.setting}"
        + (", with a stage" if b.stage else "")
    )
    if b.place and b.place.lower() not in desc.lower():
        desc += f", in {b.place}"
    draft = await venue_sources.design(_metered(config), desc)
    if draft.get("venue") is None:
        w(
            _step(
                "site",
                "failed",
                "The venue could not be designed",
                " ".join(draft.get("problems", [])),
                node="design",
            )
        )
        return {"failed": "design"}
    w(_step("site", "done", "Designed the venue", draft["venue"]["name"], node="design"))
    notes = [*state.get("notes", []), *draft.get("notes", []), *draft.get("assumptions", [])]
    return {"venue": draft["venue"], "real": False, "notes": notes}


def _with_event(venue: Venue, b: EventBrief) -> Venue:
    event = {
        "duration_h": b.duration_h,
        "alcohol": b.alcohol,
        "audience": b.audience,
        "kind": b.kind,
    }
    v = venue.model_copy(update={"extensions": {**venue.extensions, "event": event}})
    if b.start and v.location is not None:
        v = v.model_copy(
            update={"location": v.location.model_copy(update={"event_start": b.start})}
        )
    return v


async def layout(state: CopilotState, config: RunnableConfig) -> CopilotState:
    """Site layout solver: stage, barrier, front-of-house, toilets, bars, crowd bands."""
    w = get_stream_writer()
    st, b = _st(config), EventBrief.model_validate(state["brief"])
    w(_step("layout", "running", "Laying out the event on the site", node="layout"))
    venue = _with_event(Venue.model_validate(state["venue"]), b)
    est0 = compute_estimates(venue, st.registry, st.settings, st.settings.unit_costs or None)
    toilets = next((int(ln.value) for ln in est0.lines if ln.key == "toilets"), 0)
    res = furnish(venue, attendees=b.attendees, stage=b.stage, toilets=toilets, alcohol=b.alcohol)
    placed = ", ".join(dict.fromkeys(res.placed)) or "nothing new"
    w(_step("layout", "done", f"Placed {placed}", " ".join(res.notes), node="layout"))
    return {
        "venue": res.venue.model_dump(mode="json"),
        "notes": [*state.get("notes", []), *res.notes],
    }


async def estimate(state: CopilotState, config: RunnableConfig) -> CopilotState:
    """Planning ratios + egress capacity: the plan for the day."""
    w = get_stream_writer()
    st, b = _st(config), EventBrief.model_validate(state["brief"])
    venue = _with_event(Venue.model_validate(state["venue"]), b)
    w(_step("estimates", "running", "Estimating capacity, staff and facilities", node="estimate"))
    est = compute_estimates(venue, st.registry, st.settings, st.settings.unit_costs or None)
    cap, lines = est.capacity, {ln.key: ln for ln in est.lines}
    summary = (
        f"Safe capacity {cap.safe_people:,} (you plan {cap.current_people:,}) · "
        f"{int(lines['stewards'].value)} stewards · {int(lines['first_aid'].value)} first aiders · "
        f"{int(lines['toilets'].value)} toilets · budget {est.currency} {est.budget_total:,.0f}"
    )
    status = "warn" if cap.current_people > cap.safe_people else "done"
    w(
        _step(
            "estimates",
            status,
            "Estimated the plan for the day",
            summary,
            node="estimate",
            estimates=est.model_dump(mode="json"),
        )
    )
    return {"venue": venue.model_dump(mode="json"), "estimates": est.model_dump(mode="json")}


async def create(state: CopilotState, config: RunnableConfig) -> CopilotState:
    """Save the plan as a project (version 1)."""
    w = get_stream_writer()
    st, b = _st(config), EventBrief.model_validate(state["brief"])
    who = "Autopilot" if state.get("autopilot") else "the Event Copilot"
    desc = f"Planned by {who} from: “{state['text'].strip()[:300]}”"
    p = st.projects.create(b.title, venue=Venue.model_validate(state["venue"]), description=desc)
    w(
        _step(
            "project",
            "done",
            f"Created the project “{p.name}”",
            node="create",
            project_id=p.id,
            name=p.name,
        )
    )
    return {"project_id": p.id}


async def simulate(state: CopilotState, config: RunnableConfig) -> CopilotState:
    """Full crowd simulation of the plan in the sandbox (runs in the background).

    For Autopilot this is also the red-team baseline: the session reuses the same run."""
    w = get_stream_writer()
    st = _st(config)
    auto = bool(state.get("autopilot"))
    venue = st.projects.venue(state["project_id"])
    report = validate_venue(venue)
    if not report.ok or venue.total_people() > st.settings.max_people:
        why = (
            report.errors[0].message
            if not report.ok
            else (
                f"{venue.total_people():,} people is above the simulation limit "
                f"of {st.settings.max_people:,}."
            )
        )
        # the Copilot still hands over the plan; Autopilot cannot test it
        status = "failed" if auto else "warn"
        w(_step("simulate", status, "Simulation not started", why, node="simulate"))
        return {"failed": "simulate"} if auto else {}
    w(
        _step(
            "simulate",
            "running",
            f"Simulating {venue.total_people():,} people in a sandbox",
            node="simulate",
            people=venue.total_people(),
        )
    )
    p = st.projects.get(state["project_id"])
    job = st.runs.build_job(venue, tier=3, seed=42)
    rid = st.runs.submit(job, project_id=p.id, venue_version=p.current_version, label="Stress test")
    w(
        _step(
            "simulate",
            "done",
            "Full simulation started",
            "It runs in the background.",
            node="simulate",
            run_id=rid,
        )
    )
    return {"run_id": rid}


async def sweep_node(state: CopilotState, config: RunnableConfig) -> CopilotState:
    """Scenario sweep: six what-ifs, each simulated in its own sandbox branch."""
    w = get_stream_writer()
    st = _st(config)
    w(_step("sweep", "running", "Branching six what-if scenarios into sandboxes", node="sweep"))
    try:
        rec = sweep.start_sweep(st, state["project_id"], parent_run_id=state.get("run_id"))
    except Exception as exc:  # the plan is still useful without the sweep
        log.exception("sweep failed")
        w(_step("sweep", "warn", "Scenario sweep not started", str(exc)[:200], node="sweep"))
        return {}
    started = [i["label"] for i in rec["items"] if i.get("run_id")]
    runs = [str(i["run_id"]) for i in rec["items"] if i.get("run_id")]
    w(
        _step(
            "sweep",
            "done",
            f"{len(started)} scenarios queued in sandboxes",
            " · ".join(started),
            node="sweep",
            run_ids=runs,
        )
    )
    return {"sweep_runs": runs}


def _fallback_review(est: dict[str, Any]) -> dict[str, Any]:
    """Rule-based actions when the language model is unavailable."""
    actions = []
    for ln in est.get("lines", []):
        if ln["status"] != "warn":
            continue
        if ln["key"] == "capacity":
            actions.append(
                {
                    "title": "Lower the headcount or add exits",
                    "why": ln["detail"],
                    "how": "Sell fewer tickets or open more gates, then re-run the plan.",
                    "priority": 1,
                }
            )
        elif ln["key"] == "exit_width":
            actions.append(
                {
                    "title": "Add exit width",
                    "why": ln["detail"],
                    "how": "Open another gate or widen the existing ones.",
                    "priority": 1,
                }
            )
        elif ln["key"] == "barrier":
            actions.append(
                {
                    "title": "Install the front-of-stage barrier",
                    "why": ln["detail"],
                    "how": "Hire barrier sections and staff them with stewards.",
                    "priority": 2,
                }
            )
    return {
        "summary": "Rule-based review (the language model was not available).",
        "actions": actions,
    }


async def review_project(st: Any, project_id: str) -> dict[str, Any]:
    """Review any project's current plan (used outside the Copilot too)."""
    venue = st.projects.venue(project_id)
    est = compute_estimates(venue, st.registry, st.settings, st.settings.unit_costs or None)
    return await _review(st, project_id, venue, est.model_dump(mode="json"), {})


async def _review(
    st: Any, project_id: str, venue: Venue, est: dict[str, Any], brief: dict[str, Any]
) -> dict[str, Any]:
    checks = [c.message for c in validate_venue(venue).checks if c.severity != "info"][:6]
    facts = {
        "event": brief or venue.extensions.get("event", {}),
        "plan_for_the_day": [
            {"item": ln["label"], "value": ln["value"], "unit": ln["unit"], "detail": ln["detail"]}
            for ln in est.get("lines", [])
        ],
        "capacity": est.get("capacity", {}),
        "what_if_instant_estimates": sweep.instant_matrix(st, venue),
        "plan_checks": checks,
    }
    try:
        call = await review_plan(_env(st), facts)
        checked = keep_checked(call.output, facts) if call.output else None
        result = checked.model_dump(mode="json") if checked and checked.actions else None
    except AgentUnavailable:
        result = None
    if result is None:
        result = _fallback_review(est)
    save_review(st, project_id, result)
    return result


async def review(state: CopilotState, config: RunnableConfig) -> CopilotState:
    """Safety officer agent: prioritised actions, every number checked against the facts."""
    w = get_stream_writer()
    st = _st(config)
    w(_step("review", "running", "Safety officer is reviewing the plan", node="review"))
    venue = st.projects.venue(state["project_id"])
    result = await _review(
        st, state["project_id"], venue, state.get("estimates", {}), state.get("brief", {})
    )
    top = result["actions"][0]["title"] if result["actions"] else "No urgent actions"
    n = len(result["actions"])
    w(
        _step(
            "review",
            "done",
            f"Review: {n} action{'' if n == 1 else 's'}",
            f"{result['summary']} First: {top}.",
            node="review",
            review=result,
        )
    )
    return {"review": result}


def save_review(st: Any, project_id: str, review: dict[str, Any]) -> None:
    """Keep the officer's review with the project (shown in Plan)."""
    with db_session(st.projects.db_url) as s:
        row = s.get(UserSetting, f"_review:{project_id}") or UserSetting(
            key=f"_review:{project_id}"
        )
        row.value = review
        s.add(row)
        s.commit()


def load_review(st: Any, project_id: str) -> dict[str, Any] | None:
    """The officer's latest review of a project, if any."""
    with db_session(st.projects.db_url) as s:
        row = s.get(UserSetting, f"_review:{project_id}")
        return dict(row.value) if row and isinstance(row.value, dict) else None


# --- Autopilot: test the plan, then hand it over ------------------------------------------

_FORWARD = {"status", "score", "run_finished", "cost"}  # session events the driver shows


def _running_session(st: Any, project_id: str) -> Any | None:
    """A red-team session already testing this project (never start a second one)."""
    for s in st.sessions.list_sessions(project_id):
        live = st.sessions.live.get(s.id)
        if s.status == "running" and live is not None and not live.finished:
            return s
    return None


async def _follow_session(st: Any, session_id: str, w: StreamWriter) -> None:
    """Forward the session's progress into the graph stream until the session ends."""

    async def follow() -> None:
        async for ev in st.sessions.stream(session_id):
            if ev.type in _FORWARD:
                w(
                    {
                        "step": "red_team",
                        "status": "running",
                        "node": "red_team",
                        "session_event": ev.model_dump(mode="json"),
                    }
                )

    follower = asyncio.create_task(follow())
    live = st.sessions.live.get(session_id)
    task = live.task if live is not None else None
    try:
        watch = {follower} if task is None else {follower, task}
        await asyncio.wait(watch, return_when=asyncio.FIRST_COMPLETED)
        if not follower.done():  # the session ended: let its last events through
            await asyncio.wait({follower}, timeout=10)
    finally:
        if not follower.done():  # a session that died without finishing never hangs us
            follower.cancel()


def had_outage(st: Any, session_id: str) -> bool:
    """Did an agent in the session find the language model unreachable?"""
    return any(
        e.type == "agent_call"
        and not e.payload.get("ok")
        and e.payload.get("summary") == "unreachable"
        for e in st.sessions.stored_events(session_id)
    )


async def red_team(state: CopilotState, config: RunnableConfig) -> CopilotState:
    """Red Team Night on the plan (orchestrator/session.py): baseline simulation, attacks,
    fixes and the confirmation, within the session budgets. Fixes are tested, never applied."""
    w = get_stream_writer()
    st, hooks = _st(config), _hooks(config)
    if hooks is None or hooks.should_stop():
        return {"stopped": True}
    pid = state["project_id"]
    row = _running_session(st, pid) or st.sessions.start(pid, hooks.session_config)
    hooks.on_session(row.id)
    w(_step("red_team", "running", "Red team started", node="red_team", session_id=row.id))
    await _follow_session(st, row.id, w)
    return {"session_id": row.id, "outage": had_outage(st, row.id)}


def partial_reason(status: str, stopped_reason: str) -> str | None:
    """Why a tested plan is partial (None when the test ran to its natural end)."""
    if status == "stopped" or stopped_reason == "stopped by user":
        return "stopped"
    if stopped_reason.startswith("budget"):
        return "budget"
    if status != "finished" or stopped_reason.startswith("error"):
        return "error"
    return None


def _n(k: int, word: str, plural: str | None = None) -> str:
    return f"{k} {word if k == 1 else plural or word + 's'}"


def plan_headline(summary: dict[str, Any]) -> str:
    """One plain sentence about the tested plan, from recorded facts only."""
    tested = len(summary.get("attacks") or [])
    if not tested:
        return "Nothing could be tested before the test ended."
    breaks = sum(int(r.get("breaks", 0)) for r in summary.get("scoreboard") or [])
    kept = len(summary.get("accepted_fixes") or [])
    head = f"Tested {_n(tested, 'thing')} that could go wrong"
    if not breaks:
        return f"{head}: your plan held up."
    head += f"; {_n(breaks, 'broke', 'broke')} the plan."
    if kept:
        them = "it" if kept == 1 else "them"
        return f"{head} {_n(kept, 'fix', 'fixes')} worked in testing. Accept {them} on Your plan."
    return f"{head} No fix worked well enough yet."


PARTIAL_NOTES = {
    "stopped": "You stopped the test, so your plan shows what was finished.",
    "budget": "The test reached its time, simulation or AI budget. Your plan shows what was done.",
    "error": "The test hit a problem, so your plan shows what was finished.",
}
OUTAGE_NOTE = "The AI wasn't answering, so standard checks found the risks and fixes."


def cost_record(
    st: Any, session: Any | None, intake: dict[str, float], runs: Iterable[str] = ()
) -> dict[str, Any]:
    """AI tokens, money and simulations of an Autopilot run: its intake plus the session.

    The session's own cost record (summary.cost) wins when it has one; otherwise its token and
    cost fields are used."""
    red_usd = float(session.cost_usd) if session is not None else 0.0
    red_tokens = int(session.tokens) if session is not None else 0
    detail: dict[str, Any] | None = None
    calls = int(intake.get("calls", 0))
    sims = {r for r in runs if r}
    if session is not None:
        rec = (session.summary or {}).get("cost")
        if isinstance(rec, dict):
            detail = rec
            red_usd = float(rec.get("usd_total", rec.get("cost_usd", red_usd)) or 0.0)
            red_tokens = int(rec.get("tokens_total", rec.get("tokens", red_tokens)) or 0)
        for e in st.sessions.stored_events(session.id):
            p = e.payload
            if e.type == "agent_call" and int(p.get("tokens_in", 0)) + int(p.get("tokens_out", 0)):
                calls += 1
            elif e.type == "run_finished" and int(p.get("tier") or 0) >= 2:
                sims.add(str(p.get("run_id")))
    in_usd, in_tokens = float(intake.get("usd", 0.0)), int(intake.get("tokens", 0))
    return AutopilotCost(
        usd_total=round(in_usd + red_usd, 6),
        tokens_total=in_tokens + red_tokens,
        llm_calls=calls,
        simulations=len(sims),
        intake_usd=round(in_usd, 6),
        intake_tokens=in_tokens,
        red_team_usd=round(red_usd, 6),
        red_team_tokens=red_tokens,
        detail=detail,
    ).model_dump(mode="json")


async def deliver(state: CopilotState, config: RunnableConfig) -> CopilotState:
    """Writing your plan: what was tested and kept, the report and the cost record.

    Nothing is applied here: kept fixes stay proposals until the organizer accepts them."""
    w = get_stream_writer()
    st, hooks = _st(config), _hooks(config)
    w(_step("deliver", "running", "Writing your plan", node="deliver"))
    sid = state.get("session_id")
    row = st.sessions.get(sid) if sid else None
    summary: dict[str, Any] = dict(row.summary or {}) if row is not None else {}
    partial: str | None
    if row is None:
        partial = "stopped" if state.get("stopped") else "error"
    else:
        partial = partial_reason(row.status, str(summary.get("stopped_reason", "")))
    tested = row is not None and bool(summary)
    notes = [OUTAGE_NOTE] if state.get("outage") else []
    if partial:
        notes.append(PARTIAL_NOTES.get(partial, PARTIAL_NOTES["error"]))
    result = {
        "report_url": f"/api/v1/sessions/{sid}/report" if tested else None,
        "headline": plan_headline(summary) if tested else "Stopped before the plan was tested.",
        "partial_reason": partial,
        "ai_outage": bool(state.get("outage")),
        "notes": notes,
        "cost": cost_record(
            st,
            row,
            hooks.intake() if hooks is not None else {},
            [state.get("run_id", ""), *state.get("sweep_runs", [])],
        ),
    }
    w(_step("deliver", "done", str(result["headline"]), node="deliver", result=result))
    return {"result": result}


# --- the graph ------------------------------------------------------------------------------


def _route_start(state: CopilotState) -> str:
    """An existing project (Autopilot) skips straight to the simulation."""
    return "simulate" if state.get("project_id") else "understand"


def _route_after_understand(state: CopilotState) -> str:
    if state.get("failed"):
        return END
    return "locate" if state.get("brief", {}).get("place") else "design"


def _route_after_locate(state: CopilotState) -> str:
    return "layout" if state.get("real") else "design"


def _route_after_design(state: CopilotState) -> str:
    return END if state.get("failed") else "estimate"


def _route_after_simulate(state: CopilotState) -> str:
    """Copilot: the sweep. Autopilot: the sweep only when thorough, then the red team."""
    if not state.get("autopilot"):
        return "sweep"
    if state.get("failed"):
        return END
    return "sweep" if state.get("depth") == "thorough" else "red_team"


def _route_after_sweep(state: CopilotState) -> str:
    return "red_team" if state.get("autopilot") else "review"


def build_graph() -> Any:
    """The compiled Copilot/Autopilot graph (checkpointed in memory per thread)."""
    g = StateGraph(CopilotState)
    for name, fn in (
        ("understand", understand),
        ("locate", locate),
        ("design", design),
        ("layout", layout),
        ("estimate", estimate),
        ("create", create),
        ("simulate", simulate),
        ("sweep", sweep_node),
        ("review", review),
        ("red_team", red_team),
        ("deliver", deliver),
    ):
        g.add_node(name, fn)
    g.add_conditional_edges(START, _route_start, ["understand", "simulate"])
    g.add_conditional_edges("understand", _route_after_understand, ["locate", "design", END])
    g.add_conditional_edges("locate", _route_after_locate, ["layout", "design"])
    g.add_conditional_edges("design", _route_after_design, ["estimate", END])
    g.add_edge("layout", "estimate")
    g.add_edge("estimate", "create")
    g.add_edge("create", "simulate")
    g.add_conditional_edges("simulate", _route_after_simulate, ["sweep", "red_team", END])
    g.add_conditional_edges("sweep", _route_after_sweep, ["review", "red_team"])
    g.add_edge("review", END)
    g.add_edge("red_team", "deliver")
    g.add_edge("deliver", END)
    return g.compile(checkpointer=InMemorySaver())


GRAPH = build_graph()


def graph_shape() -> dict[str, Any]:
    """Nodes and edges of the compiled graph, and the Autopilot steps over them, for the UI."""
    gg = GRAPH.get_graph()
    nodes = [n for n in gg.nodes if n not in ("__start__", "__end__")]
    edges = [
        {"source": e.source, "target": e.target, "conditional": bool(e.conditional)}
        for e in gg.edges
    ]
    steps = [
        {
            "key": k,
            "label": STEP_LABELS[k],
            "nodes": list(STEP_NODES[k]),
            "phases": list(STEP_PHASES.get(k, ())),
        }
        for k in STEP_ORDER
    ]
    return {"nodes": ["__start__", *nodes, "__end__"], "edges": edges, "steps": steps}
