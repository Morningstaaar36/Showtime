"""Intent router for "Ask or change anything" (N15): model route, keyword fallback, exit names.

No live model: FakeLLM plays a working model (scripted) or a dead one (no script at all).
"""

from __future__ import annotations

import math
import re
from typing import Any

import pytest

from api.adapters.llm import FakeLLM
from api.agents.base import AgentEnv
from api.agents.router import (
    clamp_scale,
    exit_names,
    keyword_route,
    keyword_what_if,
    match_exit,
    resolve_exits,
    route_message,
)
from api.models import Venue

# T-N15-1 / T-N15-4: five utterances per intent, typed on the conference hall template
# (exits "South door 1" and "South door 2", a stage and a sound desk)
UTTERANCES: list[tuple[str, str]] = [
    ("make South door 1 three metres wide", "edit"),
    ("add a 2 m exit on the east wall", "edit"),
    ("move the sound desk 5 m north", "edit"),
    ("remove the sound desk", "edit"),
    ("put 1000 people in the audience area", "edit"),
    ("why is it crowded near the stage?", "question"),
    ("how long does it take to get everyone out?", "question"),
    ("which exit is the busiest?", "question"),
    ("when does the crowd get dangerous?", "question"),
    ("what is the peak density?", "question"),
    ("what if it rains?", "what_if"),
    ("what if twice as many people come?", "what_if"),
    ("close South door 2", "what_if"),
    ("if South door 1 is blocked, how bad is it?", "what_if"),
    ("suppose there is smoke and 50% more people", "what_if"),
    ("download the report", "navigate"),
    ("open the expert view", "navigate"),
    ("take me back to my plan", "navigate"),
    ("show the AI test progress", "navigate"),
    ("go back to the venue check", "navigate"),
]
EXPECTED = dict(UTTERANCES)
MESSAGE = re.compile(r'Message: "(.*)"', re.DOTALL)


def _env(script: dict[str, Any]) -> tuple[AgentEnv, FakeLLM]:
    llm = FakeLLM(script)
    return AgentEnv(llm=llm, audit=False), llm


def _model_that_knows(messages: list[dict[str, str]]) -> dict[str, Any]:
    """A model that sorts every eval utterance correctly (the model route's plumbing)."""
    m = MESSAGE.search(messages[-1]["content"])
    assert m is not None
    return {"intent": EXPECTED[m.group(1)]}


def test_the_eval_set_has_five_utterances_per_intent() -> None:
    counts = {i: sum(want == i for _, want in UTTERANCES) for i in set(EXPECTED.values())}
    assert counts == {"edit": 5, "question": 5, "what_if": 5, "navigate": 5}


async def test_keyword_fallback_routes_the_eval_set_with_the_model_down(hall: Venue) -> None:
    env, llm = _env({})  # no script: every call fails like an unreachable server
    routes = [await route_message(env, hall, text) for text, _ in UTTERANCES]
    assert all(r.routed_by == "keywords" for r in routes)
    right = sum(r.intent == want for r, (_, want) in zip(routes, UTTERANCES, strict=True))
    assert right >= 14, f"keyword fallback routed {right}/20"
    assert len(llm.calls) == len(UTTERANCES)  # one attempt each, nothing retried on a dead model


async def test_the_model_route_is_used_when_the_model_answers(hall: Venue) -> None:
    env, llm = _env({"router": _model_that_knows})
    routes = [await route_message(env, hall, text, "plan") for text, _ in UTTERANCES]
    assert [r.intent for r in routes] == [want for _, want in UTTERANCES]
    assert all(r.routed_by == "model" for r in routes)
    system = llm.calls[0][1][0]["content"]
    assert "South door 1; South door 2" in system and "reading the tested plan" in system
    assert "{{" not in system  # every placeholder filled


async def test_what_if_parameters_come_from_the_model(hall: Venue) -> None:
    env, _ = _env(
        {"router": {"intent": "what_if", "crowd_scale": 2, "weather": "rain", "closed_exits": []}}
    )
    route = await route_message(env, hall, "what if it pours and the crowd doubles?")
    assert (route.intent, route.routed_by) == ("what_if", "model")
    assert route.crowd_scale == 2 and route.weather == "rain" and route.closed_exits == []


async def test_small_model_spellings_are_accepted(hall: Venue) -> None:
    out = {
        "intent": "What-If",
        "weather": "Darkness",
        "closed_exits": "south door 2",
        "people": 2400,
    }
    env, _ = _env({"router": out})
    route = await route_message(env, hall, "2400 people, lights out, south door 2 shut")
    assert (route.intent, route.routed_by) == ("what_if", "model")
    assert route.weather == "smoke" and route.closed_exits == ["south door 2"]
    assert route.crowd_scale == 2.0  # 2400 people of the 1200 planned


async def test_an_empty_model_what_if_reads_the_words(hall: Venue) -> None:
    env, _ = _env({"router": {"intent": "what_if"}})
    route = await route_message(env, hall, "what if it rains and twice as many people come?")
    assert route.routed_by == "model" and route.crowd_scale == 2.0 and route.weather == "rain"


async def test_navigation_needs_a_destination(hall: Venue) -> None:
    env, _ = _env({"router": [{"intent": "navigate"}, {"intent": "navigate"}]})
    found = await route_message(env, hall, "open the expert view")
    assert (found.intent, found.target) == ("navigate", "expert")
    lost = await route_message(env, hall, "go somewhere nice")
    assert (lost.intent, lost.target) == ("other", None)


async def test_unusable_model_answers_fall_back_to_keywords(hall: Venue) -> None:
    env, llm = _env({"router": ["Sure! That is a question.", "Still prose."]})
    route = await route_message(env, hall, "why is it crowded?")
    assert (route.intent, route.routed_by) == ("question", "keywords")
    # the fast answer, one escalation to main (test_escalation.py), then the keywords decide
    assert [agent for agent, _ in llm.calls] == ["router", "router"]


async def test_absurd_numbers_never_break_the_router(hall: Venue) -> None:
    env, _ = _env({"router": {"intent": "what_if", "crowd_scale": math.inf}})
    route = await route_message(env, hall, "what if " + "9" * 400 + " people come?")
    assert (route.intent, route.routed_by, route.crowd_scale) == ("what_if", "keywords", None)
    assert keyword_what_if("what if 12345% more people come", hall)[0] is None


@pytest.mark.parametrize(
    ("text", "scale", "weather", "closed"),
    [
        ("what if it rains?", None, "rain", []),
        ("what if twice as many people come?", 2.0, None, []),
        ("what if 3,000 people come", 2.5, None, []),
        ("what if 600 more people come in a blackout", 1.5, "smoke", []),
        ("suppose there is smoke and 50% more people", 1.5, "smoke", []),
        ("if South door 1 is blocked, how bad is it?", None, None, ["South door 1"]),
        ("close South door 2 and the VIP gate", None, None, ["South door 2", "VIP gate"]),
        ("what if the south door 1 is closed and it rains", None, "rain", ["south door 1"]),
        ("what if South door 1 shuts down", None, None, ["South door 1"]),
    ],
)
def test_keyword_what_if_reads_scale_weather_and_exits(
    hall: Venue, text: str, scale: float | None, weather: str | None, closed: list[str]
) -> None:
    assert keyword_what_if(text, hall) == (scale, weather, closed)


def test_keyword_navigation_targets(hall: Venue) -> None:
    cases = {
        "download the report": "report",
        "how do I open the report?": "report",
        "expert view": "expert",
        "take me back to my plan": "plan",
        "show the AI test progress": "work",
        "go back to the venue check": "check",
    }
    for text, target in cases.items():
        route = keyword_route(text, hall)
        assert (route.intent, route.target) == ("navigate", target), text
    assert keyword_route("open South door 1", hall).intent == "edit"  # a door, not a screen
    assert keyword_route("hello there", hall).intent == "other"


def test_exit_names_match_names_and_ids_but_never_guess(hall: Venue, field: Venue) -> None:
    names = exit_names(hall)
    assert names == {"door_s1": "South door 1", "door_s2": "South door 2"}
    assert match_exit("south door 1", names) == "door_s1"
    assert match_exit("DOOR_S2", names) == "door_s2"
    assert match_exit("the South Door 1", names) == "door_s1"
    assert match_exit("door 1", names) == "door_s1"
    assert match_exit("south door", names) is None  # both fit: ask, don't guess
    assert match_exit("door 10", names) is None
    gates = exit_names(field)
    assert match_exit("south-west gate", gates) == "gate_sw"
    assert match_exit("west gate", gates) == "gate_sw"
    assert resolve_exits(["South door 2", "door_s2", "VIP gate"], hall) == (
        ["door_s2"],
        ["VIP gate"],
    )


def test_unlabelled_exits_are_named_like_the_ui(hall: Venue) -> None:
    venue = hall.model_copy(deep=True)
    for e in venue.floors[0].exits:
        e.label = None  # e.g. drawn in the editor without a name
    names = exit_names(venue)
    # web/src/lib/venueText.ts exitName(); two alike get their id so each name fits one exit
    assert names == {"door_s1": "New south exit (door_s1)", "door_s2": "New south exit (door_s2)"}
    assert match_exit("New south exit (door_s2)", names) == "door_s2"
    assert match_exit("new south exit", names) is None
    venue.floors[0].exits.pop()
    assert exit_names(venue) == {"door_s1": "New south exit"}


@pytest.mark.parametrize(
    ("asked", "used", "capped"),
    [
        (10.0, 3.0, True),
        (0.1, 0.25, True),
        (2.0, 2.0, False),
        (0.25, 0.25, False),
        (None, 1.0, False),
        (-1.0, 1.0, False),
        (math.nan, 1.0, False),
    ],
)
def test_crowd_scale_is_clamped_to_a_quarter_to_three_times(
    asked: float | None, used: float, capped: bool
) -> None:
    assert clamp_scale(asked) == (used, capped)
