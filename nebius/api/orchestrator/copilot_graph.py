"""Event Copilot as a LangGraph state graph.

understand → (place named?) locate → (real site?) layout | design → estimate → create →
simulate → sweep → review. Each node streams progress through LangGraph's custom stream, and the
graph's own structure is served to the UI so it can be drawn as the agents work.
"""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

from api.agents.base import AgentEnv, AgentUnavailable
from api.agents.event_brief import read_brief
from api.agents.safety_officer import keep_checked, review_plan
from api.core.estimates import compute_estimates
from api.core.geometry import validate_venue
from api.core.site_layout import furnish
from api.db.models import UserSetting
from api.db.session import db_session
from api.models import Venue
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


def _st(config: RunnableConfig) -> Any:
    return config["configurable"]["st"]


def _env(st: Any) -> AgentEnv:
    return AgentEnv(llm=st.llm, project_id=None, on_usage=st.usage.add)


async def understand(state: CopilotState, config: RunnableConfig) -> CopilotState:
    """Brief agent: the request → event brief."""
    w = get_stream_writer()
    w(_step("brief", "running", "Reading your request", node="understand"))
    call = await read_brief(_env(_st(config)), state["text"])
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
    draft = await venue_sources.design(_st(config), desc)
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
    desc = f"Planned by the Event Copilot from: “{state['text'].strip()[:300]}”"
    p = st.projects.create(b.title, venue=Venue.model_validate(state["venue"]), description=desc)
    w(_step("project", "done", f"Created the project “{p.name}”", node="create", project_id=p.id))
    return {"project_id": p.id}


async def simulate(state: CopilotState, config: RunnableConfig) -> CopilotState:
    """Full crowd simulation of the plan in the sandbox (runs in the background)."""
    w = get_stream_writer()
    st = _st(config)
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
        w(_step("simulate", "warn", "Simulation not started", why, node="simulate"))
        return {}
    w(
        _step(
            "simulate",
            "running",
            f"Simulating {venue.total_people():,} people in a sandbox",
            node="simulate",
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
    w(
        _step(
            "sweep",
            "done",
            f"{len(started)} scenarios queued in sandboxes",
            " · ".join(started),
            node="sweep",
        )
    )
    return {}


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


def _route_after_understand(state: CopilotState) -> str:
    if state.get("failed"):
        return END
    return "locate" if state.get("brief", {}).get("place") else "design"


def _route_after_locate(state: CopilotState) -> str:
    return "layout" if state.get("real") else "design"


def _route_after_design(state: CopilotState) -> str:
    return END if state.get("failed") else "estimate"


def build_graph() -> Any:
    """The compiled Copilot graph (checkpointed in memory per thread)."""
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
    ):
        g.add_node(name, fn)
    g.add_edge(START, "understand")
    g.add_conditional_edges("understand", _route_after_understand, ["locate", "design", END])
    g.add_conditional_edges("locate", _route_after_locate, ["layout", "design"])
    g.add_conditional_edges("design", _route_after_design, ["estimate", END])
    g.add_edge("layout", "estimate")
    g.add_edge("estimate", "create")
    g.add_edge("create", "simulate")
    g.add_edge("simulate", "sweep")
    g.add_edge("sweep", "review")
    g.add_edge("review", END)
    return g.compile(checkpointer=InMemorySaver())


GRAPH = build_graph()


def graph_shape() -> dict[str, Any]:
    """Nodes and edges of the compiled graph, for drawing it in the UI."""
    gg = GRAPH.get_graph()
    nodes = [n for n in gg.nodes if n not in ("__start__", "__end__")]
    edges = [
        {"source": e.source, "target": e.target, "conditional": bool(e.conditional)}
        for e in gg.edges
    ]
    return {"nodes": ["__start__", *nodes, "__end__"], "edges": edges}
