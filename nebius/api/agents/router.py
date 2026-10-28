"""Router agent for the one box "Ask or change anything" (N15).

The `fast` model sorts a message into edit / question / what_if / analyse / navigate / other
and pulls out what-if parameters. "analyse" is a question answered by code the analyst writes
and runs in a sandbox (queues, counts, averages, the worst minute, a chart). When the model
is unreachable, or its answer stays unusable after the repair round and one escalation to
`main`, a keyword router decides instead. Exit names are always matched to the venue in
code; a name that fits no exit is reported, never guessed.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from api.adapters.llm import LLMReplayMiss
from api.agents.base import AgentDef, AgentEnv, AgentUnavailable, call_agent
from api.agents.context import wall_of
from api.core.scenarios import RAIN_SPEED, SMOKE_SPEED
from api.models import Venue

Intent = Literal["edit", "question", "what_if", "analyse", "navigate", "other"]
Target = Literal["report", "expert", "plan", "check", "work"]
Weather = Literal["rain", "smoke", "none"]
Screen = Literal["check", "plan"]

CROWD_SCALE_MIN, CROWD_SCALE_MAX = 0.25, 3.0
# walking-speed factors: the same presets as the What-if lab in Expert view
WEATHER_SPEED: dict[str, float] = {"rain": RAIN_SPEED, "smoke": SMOKE_SPEED, "none": 1.0}
SCREENS: dict[str, str] = {"check": "checking the venue", "plan": "reading the tested plan"}


def _alias(value: Any, aliases: dict[str, str | None]) -> Any:
    """Small models write "what if" or "expert view": map such words onto the schema values."""
    if not isinstance(value, str):
        return value
    key = re.sub(r"[\s_-]+", " ", value.strip().lower())
    return aliases[key] if key in aliases else key.replace(" ", "_")


_NONE: dict[str, str | None] = {"": None, "null": None, "none": None, "n/a": None}
_INTENT_ALIASES: dict[str, str | None] = {
    "whatif": "what_if",
    "scenario": "what_if",
    "change": "edit",
    "navigation": "navigate",
    "go to": "navigate",
    "ask": "question",
    "analyze": "analyse",
    "analysis": "analyse",
    "data analysis": "analyse",
}
_WEATHER_ALIASES: dict[str, str | None] = {
    **_NONE,
    "none": "none",
    "rainy": "rain",
    "raining": "rain",
    "wet": "rain",
    "smoky": "smoke",
    "dark": "smoke",
    "darkness": "smoke",
    "blackout": "smoke",
    "power cut": "smoke",
    "clear": "none",
    "dry": "none",
    "normal": "none",
}
_TARGET_ALIASES: dict[str, str | None] = {
    **_NONE,
    "expert view": "expert",
    "expert mode": "expert",
    "studio": "expert",
    "progress": "work",
    "ai at work": "work",
    "test": "work",
    "testing": "work",
    "venue": "check",
    "venue check": "check",
    "check venue": "check",
    "your plan": "plan",
    "my plan": "plan",
    "results": "plan",
    "pdf": "report",
    "download": "report",
}


class RouteOut(BaseModel):
    """What the router model returns."""

    intent: Intent
    crowd_scale: float | None = Field(default=None, allow_inf_nan=False)
    people: int | None = Field(default=None, ge=0, le=10_000_000)
    weather: Weather | None = None
    closed_exits: list[str] = Field(default_factory=list, max_length=12)
    target: Target | None = None

    @field_validator("intent", mode="before")
    @classmethod
    def _intent(cls, v: Any) -> Any:
        return _alias(v, _INTENT_ALIASES)

    @field_validator("weather", mode="before")
    @classmethod
    def _weather(cls, v: Any) -> Any:
        return _alias(v, _WEATHER_ALIASES)

    @field_validator("target", mode="before")
    @classmethod
    def _target(cls, v: Any) -> Any:
        return _alias(v, _TARGET_ALIASES)

    @field_validator("closed_exits", mode="before")
    @classmethod
    def _exits(cls, v: Any) -> Any:
        if v is None:
            return []
        return [v] if isinstance(v, str) else v


ROUTER_AGENT = AgentDef(
    name="router",
    role="fast",
    prompt_file="router.md",
    output_model=RouteOut,
    temperature=0.0,
    max_tokens=250,
    description="Sorts one-box requests into edit, question, what-if or navigation.",
)


@dataclass
class Route:
    """The decision, whoever made it."""

    intent: Intent
    routed_by: Literal["model", "keywords"]
    crowd_scale: float | None = None
    weather: Literal["rain", "smoke"] | None = None
    closed_exits: list[str] = field(default_factory=list)  # as written; matched in code
    target: Target | None = None


def clamp_scale(scale: float | None) -> tuple[float, bool]:
    """(crowd scale to use, whether it was capped to 0.25–3). No usable value: 1, unchanged."""
    if scale is None or not math.isfinite(scale) or scale <= 0:
        return 1.0, False
    used = min(CROWD_SCALE_MAX, max(CROWD_SCALE_MIN, scale))
    return round(used, 3), used != scale


# --- exit names ------------------------------------------------------------------------------


def _norm(s: str) -> str:
    s = re.sub(r"[-_/]+", " ", s.lower())
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"^(?:the|a|an) ", "", " ".join(s.split()))


def _has_words(hay: str, needle: str) -> bool:
    return bool(needle) and f" {needle} " in f" {hay} "


def exit_names(venue: Venue) -> dict[str, str]:
    """Exit id → the name the organizer sees: its label, else "New east exit" (as in the UI).

    Two exits with the same name get their id added, so every name points at one exit.
    """
    names: dict[str, str] = {}
    for f in venue.floors:
        for e in f.exits:
            names[e.id] = e.label or f"New {wall_of(venue, f.floor_id, e.polygon)[0]} exit"
    seen = Counter(names.values())
    return {eid: f"{n} ({eid})" if seen[n] > 1 else n for eid, n in names.items()}


def match_exit(name: str, names: dict[str, str]) -> str | None:
    """The exit an organizer means by `name` (its name or id, any case), if exactly one fits."""
    n = _norm(name)
    if not n:
        return None
    exact = [eid for eid, label in names.items() if n in (_norm(label), _norm(eid))]
    if exact:
        return exact[0] if len(exact) == 1 else None
    if len(n) < 3:
        return None
    hits = [
        eid
        for eid, label in names.items()
        if _has_words(_norm(label), n) or _has_words(n, _norm(label))
    ]
    return hits[0] if len(hits) == 1 else None


def resolve_exits(written: list[str], venue: Venue) -> tuple[list[str], list[str]]:
    """(exit ids, names that fit no exit) for exit names as the organizer wrote them."""
    names = exit_names(venue)
    ids: list[str] = []
    unknown: list[str] = []
    for raw in written:
        eid = match_exit(raw, names)
        if eid is None:
            if raw.strip() and raw.strip() not in unknown:
                unknown.append(raw.strip())
        elif eid not in ids:
            ids.append(eid)
    return ids, unknown


# --- keyword router --------------------------------------------------------------------------

_WHAT_IF_PHRASE = re.compile(
    r"\b(what if|what happens if|what would happen if|suppose|imagine)\b|^if\b"
)
# a navigation verb at the start, after an optional polite lead ("can you", "how do i")
_NAV_START = re.compile(
    r"^(?:please |ok |okay |now |can you |could you |can i |could i |how do i |how can i |"
    r"i want to |i d like to |i would like to |let me |let s |lets )*"
    r"(?:open|show|go|get|take|bring|switch|jump|back|view|see|return)\b"
)
_NAV_ALWAYS = re.compile(r"\b(download|print|export)\b")
_NAV_TARGETS: list[tuple[Target, re.Pattern[str]]] = [
    ("report", re.compile(r"\b(report|pdf|printout|download|print|export)\b")),
    ("expert", re.compile(r"\b(expert|studio|advanced)\b")),
    ("work", re.compile(r"\b(progress|ai at work|test running|the test|testing)\b")),
    (
        "check",
        re.compile(
            r"\b(venue check|check(ing)? (the |my )?venue|check screen|venue screen)\b"
            r"|\bback to the venue\b"
        ),
    ),
    ("plan", re.compile(r"\b(my plan|the plan|your plan|plan screen|results?)\b")),
]
_QUESTION = re.compile(
    r"^(why|how|what|whats|when|where|which|who|is|are|does|do|did|can|could|will|would|"
    r"should|was|were|tell me|explain|show me (where|why|how|what|which|when))\b"
)
# questions answered best by computing over the trajectories (the analyst writes the code)
_ANALYSE = re.compile(
    r"\b(how long|how many|which minute|what minute|queue|queues|queued|queuing|queueing|"
    r"average|averages|chart|graph|plot|busiest)\b"
)
_WHAT_IF_WORDS = re.compile(
    r"\b(close|closed|closes|closing|shut|shuts|block|blocked|lose|lost|double|doubled|twice|"
    r"triple|tripled|half|halve|halved|rain|rains|raining|rainy|storm|smoke|smoky|dark|darkness|"
    r"blackout|power cut|power out)\b"
)
_EDIT = re.compile(
    r"\b(add|remove|delete|move|shift|set|widen|narrow|make|resize|enlarge|shrink|put|place|"
    r"open|insert|extend|increase|reduce|change|rename|lock|unlock|turn|swap|replace|wider|"
    r"narrower|bigger|smaller)\b|\b\d+(?:\.\d+)?\s*(?:m|metres?|meters?)\b"
)


def keyword_target(text: str) -> Target | None:
    """Where a navigation request points, from its words."""
    t = _norm(text)
    for target, pattern in _NAV_TARGETS:
        if pattern.search(t):
            return target
    return None


def keyword_intent(text: str) -> Intent:
    """Intent from words alone (used when the model is down or unusable)."""
    raw = text.strip().lower()
    t = _norm(raw)
    if _WHAT_IF_PHRASE.search(t):
        return "what_if"
    target = keyword_target(t)
    if target is not None:
        if _NAV_START.search(t) or _NAV_ALWAYS.search(t):
            return "navigate"
        # a bare destination: "report", "expert view", "progress"
        if len(t.split()) <= 4 and not raw.endswith("?") and target in ("report", "expert", "work"):
            return "navigate"
    if _ANALYSE.search(t):
        return "analyse"
    if _QUESTION.search(t) or raw.endswith("?"):
        return "question"
    if _WHAT_IF_WORDS.search(t):
        return "what_if"
    if _EDIT.search(t):
        return "edit"
    return "other"


# bounded digit runs: a 400-digit number must not overflow a float
_PCT = re.compile(
    r"\b(\d{1,4}(?:\.\d{1,3})?)\s*(?:%|percent)\s*(more|bigger|larger|extra|fewer|less|smaller)"
)
_TIMES = re.compile(r"\b(\d{1,3}(?:\.\d{1,3})?)\s*(?:x|times)\b")
_SCALE_WORDS: list[tuple[re.Pattern[str], float]] = [
    (re.compile(r"\b(double|doubled|twice|two times)\b"), 2.0),
    (re.compile(r"\b(triple|tripled|three times)\b"), 3.0),
    (re.compile(r"\b(half|halve|halved)\b"), 0.5),
]
_PEOPLE = r"(?:people|persons|visitors|guests|fans|attendees|spectators)"
_NUM = r"(\d{1,3}(?:,\d{3}){1,3}|\d{1,9})"
_DELTA = re.compile(rf"\b{_NUM}\s*(more|extra|additional|fewer|less)\s*{_PEOPLE}\b")
_COUNT = re.compile(rf"\b{_NUM}\s*{_PEOPLE}\b")
_RAIN = re.compile(r"\b(rain|rains|raining|rainy|wet|storm|stormy|downpour)\b")
_SMOKE = re.compile(
    r"\b(smoke|smoky|fire|dark|darkness|blackout|fog|power (?:cut|out|failure|fails))\b"
    r"|\b(?:lose|lost|no) power\b"
)
_CLOSE_VERB = r"(?:close|closed|closes|closing|shut|shuts|block|blocked|blocks|lose|lost|loses)"
_BE = r"(?:is|are|was|were|gets|get|got|becomes|become|stays)"
_STOP = (
    r"(?=\s+(?:if|while|when|during|but|so|then|because|with|after|before|for|at|from|until)"
    r"\b|[?.!;:]|$)"
)
# run on the organizer's own text, so an unknown name is reported as they wrote it
_AFTER_VERB = re.compile(rf"\b{_CLOSE_VERB}\s+(?:off\s+|down\s+)?(.+?){_STOP}", re.IGNORECASE)
_BEFORE_VERB = re.compile(rf"(.+?)\s+{_BE}\s+(?:also\s+)?{_CLOSE_VERB}\b", re.IGNORECASE)
_LEAD = re.compile(
    r"^(?:what if|what happens if|if|suppose|imagine|and|but|so|the|a|an)\s+", re.IGNORECASE
)
_TAIL = re.compile(rf"\s+{_BE}\b.*$", re.IGNORECASE)
_EXITISH = re.compile(
    r"\b(door|doors|gate|gates|exit|exits|entrance|entrances|stair|stairs|stairwell|stairway|"
    r"way out|alley|street|road|end|corridor|ramp|bridge)\b"
)


def keyword_scale(text: str, people_now: int) -> float | None:
    """Crowd scale from "twice as many", "30% more", "3x", "500 more people" or "3000 people"."""
    t = text.lower()
    pct = _PCT.search(t)
    if pct:
        p = float(pct.group(1)) / 100
        return 1 + p if pct.group(2) in ("more", "bigger", "larger", "extra") else 1 - p
    times = _TIMES.search(t)
    if times:
        return float(times.group(1))
    for pattern, value in _SCALE_WORDS:
        if pattern.search(t):
            return value
    if people_now > 0:
        delta = _DELTA.search(t)
        if delta:
            n = int(delta.group(1).replace(",", ""))
            sign = 1 if delta.group(2) in ("more", "extra", "additional") else -1
            return (people_now + sign * n) / people_now
        count = _COUNT.search(t)
        if count:
            return int(count.group(1).replace(",", "")) / people_now
    return None


def keyword_closed_exits(text: str, venue: Venue) -> list[str]:
    """Exits a what-if closes ("close the north gate", "if South door 1 is blocked").

    Phrases that fit an exit, or that sound like one ("the VIP gate"), are kept as written so
    that an unknown name is reported; other words after "close" ("close it") are ignored.
    """
    if not re.search(rf"\b{_CLOSE_VERB}\b", text, re.IGNORECASE):
        return []
    names = exit_names(venue)
    phrases = [m.group(1) for m in _AFTER_VERB.finditer(text)]
    phrases += [m.group(1) for m in _BEFORE_VERB.finditer(text)]
    found: list[str] = []
    for phrase in phrases:
        for part in re.split(r"\s*(?:,|&|\band\b|\bor\b)\s*", phrase, flags=re.IGNORECASE):
            part = _TAIL.sub("", part.strip())  # "the south gate is blocked" → "the south gate"
            while _LEAD.match(part):
                part = _LEAD.sub("", part, count=1)
            part = part.strip(" '\"")
            if not part or part.lower() in (f.lower() for f in found):
                continue
            if match_exit(part, names) is not None or _EXITISH.search(part.lower()):
                found.append(part)
    if not found:  # "what if South door 1 shuts down": names written anywhere in the text
        nt = _norm(text)
        found = [n for n in names.values() if _has_words(nt, _norm(n))]
    return found


def keyword_what_if(
    text: str, venue: Venue
) -> tuple[float | None, Literal["rain", "smoke"] | None, list[str]]:
    """Crowd scale, weather and closed exits mentioned in a what-if sentence."""
    t = _norm(text)
    weather: Literal["rain", "smoke"] | None = None
    if _RAIN.search(t):
        weather = "rain"
    elif _SMOKE.search(t):
        weather = "smoke"
    return keyword_scale(text, venue.total_people()), weather, keyword_closed_exits(text, venue)


def keyword_route(text: str, venue: Venue) -> Route:
    """The keyword router's full decision."""
    route = Route(intent=keyword_intent(text), routed_by="keywords")
    if route.intent == "what_if":
        route.crowd_scale, route.weather, route.closed_exits = keyword_what_if(text, venue)
    elif route.intent == "navigate":
        route.target = keyword_target(text)
    return _settled(route)


def _settled(route: Route) -> Route:
    """A navigation request without a destination is answered with help instead."""
    if route.intent == "navigate" and route.target is None:
        route.intent = "other"
    return route


# --- model router ----------------------------------------------------------------------------


def _from_model(out: RouteOut, text: str, venue: Venue) -> Route:
    route = Route(intent=out.intent, routed_by="model")
    if out.intent == "what_if":
        scale = out.crowd_scale
        if scale is None and out.people and venue.total_people() > 0:
            scale = out.people / venue.total_people()
        route.crowd_scale = scale
        route.weather = out.weather if out.weather in ("rain", "smoke") else None
        route.closed_exits = [n.strip() for n in out.closed_exits if n.strip()]
        if route.crowd_scale is None and route.weather is None and not route.closed_exits:
            # the model saw a what-if but filled nothing in: read the numbers from the words
            route.crowd_scale, route.weather, route.closed_exits = keyword_what_if(text, venue)
    elif out.intent == "navigate":
        route.target = out.target or keyword_target(text)
    return _settled(route)


async def route_message(env: AgentEnv, venue: Venue, text: str, screen: Screen = "check") -> Route:
    """Ask the `fast` model; fall back to keywords when it is down or answers unusably."""
    values = {
        "exits": "; ".join(exit_names(venue).values()) or "none",
        "people": str(venue.total_people()),
        "screen": SCREENS[screen],
    }
    try:
        call = await call_agent(
            env,
            ROUTER_AGENT,
            values,
            f'Message: "{text.strip()[:300]}"',
            output_model=RouteOut,
            summarize=lambda o: o.intent,
        )
    except (AgentUnavailable, LLMReplayMiss):
        return keyword_route(text, venue)
    if call.output is None:  # still invalid after the repair round and the escalation
        return keyword_route(text, venue)
    return _from_model(call.output, text, venue)
