"""Built-in scenario events (ScenarioEvent extension point).

Each event has a schema, a reference check, a Tier 1 effect and a UI label. The
matching sim-side handlers live in `sim/plugins/events.py` inside the sandbox image.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.core.extensions import Registry, T1Group, Tier1State
from api.core.scripts import MAX_SCRIPT_CHARS, check_script
from api.models import Venue

COUNTERFLOW_CAPACITY_FACTOR = 0.5  # usable width halves when a group pushes the other way
SURGE_ID_PREFIX = "surge:"


class Config(BaseModel):
    """No settings yet."""


class _E(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str
    at_s: float = Field(default=0.0, ge=0, le=3600)


def _exit_ids(v: Venue) -> set[str]:
    return {e.id for f in v.floors for e in f.exits}


def _zone_ids(v: Venue) -> set[str]:
    return {z.id for f in v.floors for z in f.zones}


class BlockExitEvent(_E):
    type: Literal["block_exit"] = "block_exit"
    exit_id: str


class BlockExit:
    type = "block_exit"
    label = "Exit blocked"
    description = "An exit becomes unusable at at_s (crowd, fire, police line, locked gate)."
    params_model = BlockExitEvent

    def validate_refs(self, venue: Venue, p: BlockExitEvent) -> list[str]:
        return [] if p.exit_id in _exit_ids(venue) else [f"Unknown exit '{p.exit_id}'."]

    def tier1_effect(self, state: Tier1State, p: BlockExitEvent) -> None:
        ex = state.exits.get(p.exit_id)
        if ex is not None:
            cur = ex.blocked_from_s
            ex.blocked_from_s = p.at_s if cur is None else min(cur, p.at_s)


class UnblockExitEvent(_E):
    type: Literal["unblock_exit"] = "unblock_exit"
    exit_id: str


class UnblockExit:
    type = "unblock_exit"
    label = "Exit reopened"
    description = "A blocked exit becomes usable again at at_s."
    params_model = UnblockExitEvent

    def validate_refs(self, venue: Venue, p: UnblockExitEvent) -> list[str]:
        return [] if p.exit_id in _exit_ids(venue) else [f"Unknown exit '{p.exit_id}'."]

    def tier1_effect(self, state: Tier1State, p: UnblockExitEvent) -> None:
        ex = state.exits.get(p.exit_id)
        if ex is not None and ex.blocked_from_s is not None and p.at_s <= ex.blocked_from_s:
            ex.blocked_from_s = None
        elif ex is not None and ex.blocked_from_s is not None:
            state.notes.append(f"Instant estimate treats {p.exit_id} as blocked until the end.")


class SurgeEvent(_E):
    type: Literal["surge"] = "surge"
    zone_id: str
    extra_people: int = Field(gt=0, le=20_000)


class Surge:
    type = "surge"
    label = "Crowd surge"
    description = "Extra people arrive in a zone at at_s (late arrivals, gate rush)."
    params_model = SurgeEvent

    def validate_refs(self, venue: Venue, p: SurgeEvent) -> list[str]:
        return [] if p.zone_id in _zone_ids(venue) else [f"Unknown zone '{p.zone_id}'."]

    def tier1_effect(self, state: Tier1State, p: SurgeEvent) -> None:
        base = state.groups.get(p.zone_id)
        if base is None:
            return
        key = f"{SURGE_ID_PREFIX}{p.zone_id}:{int(p.at_s)}"
        g = state.groups.get(key)
        if g:
            g.people += p.extra_people
        else:
            state.groups[key] = T1Group(
                id=key,
                floor_id=base.floor_id,
                x=base.x,
                y=base.y,
                people=p.extra_people,
                release_s=p.at_s,
                speed_factor=base.speed_factor,
            )


class SlowdownEvent(_E):
    type: Literal["slowdown"] = "slowdown"
    factor: float = Field(gt=0.05, le=1.0)
    zone_id: str | None = None


class Slowdown:
    type = "slowdown"
    label = "Slowdown"
    description = "Walking speed drops by a factor from at_s (power cut, smoke, slope, rain)."
    params_model = SlowdownEvent

    def validate_refs(self, venue: Venue, p: SlowdownEvent) -> list[str]:
        if p.zone_id and p.zone_id not in _zone_ids(venue):
            return [f"Unknown zone '{p.zone_id}'."]
        return []

    def tier1_effect(self, state: Tier1State, p: SlowdownEvent) -> None:
        if p.zone_id:
            for g in state.groups.values():
                if g.id == p.zone_id or g.id.startswith(f"{SURGE_ID_PREFIX}{p.zone_id}:"):
                    g.speed_factor *= p.factor
        else:
            state.global_speed_factor *= p.factor


class CounterflowEvent(_E):
    type: Literal["counterflow"] = "counterflow"
    exit_id: str
    people: int = Field(gt=0, le=10_000)
    target_zone_id: str | None = None


class Counterflow:
    type = "counterflow"
    label = "Counterflow"
    description = (
        "A group enters through an exit and pushes inward against the evacuating crowd "
        "(late arrivals, people going back for friends)."
    )
    params_model = CounterflowEvent

    def validate_refs(self, venue: Venue, p: CounterflowEvent) -> list[str]:
        errs = [] if p.exit_id in _exit_ids(venue) else [f"Unknown exit '{p.exit_id}'."]
        if p.target_zone_id and p.target_zone_id not in _zone_ids(venue):
            errs.append(f"Unknown zone '{p.target_zone_id}'.")
        return errs

    def tier1_effect(self, state: Tier1State, p: CounterflowEvent) -> None:
        ex = state.exits.get(p.exit_id)
        if ex is not None:
            ex.capacity_pps *= COUNTERFLOW_CAPACITY_FACTOR
            state.notes.append(f"Counterflow at {p.exit_id}: instant estimate halves its capacity.")


class StaggeredReleaseEvent(_E):
    type: Literal["staggered_release"] = "staggered_release"
    zone_id: str
    delay_s: float = Field(gt=0, le=1800)


class StaggeredRelease:
    type = "staggered_release"
    label = "Staggered release"
    description = "Hold a zone back for delay_s before it starts leaving (marshals, announcements)."
    params_model = StaggeredReleaseEvent

    def validate_refs(self, venue: Venue, p: StaggeredReleaseEvent) -> list[str]:
        return [] if p.zone_id in _zone_ids(venue) else [f"Unknown zone '{p.zone_id}'."]

    def tier1_effect(self, state: Tier1State, p: StaggeredReleaseEvent) -> None:
        g = state.groups.get(p.zone_id)
        if g is not None:
            g.release_s = max(g.release_s, p.at_s + p.delay_s)


class MarshalRedirectEvent(_E):
    type: Literal["marshal_redirect"] = "marshal_redirect"
    to_exit_id: str
    from_exit_id: str | None = None
    x: float | None = None
    y: float | None = None
    radius_m: float = Field(default=8.0, gt=0, le=100)
    fraction: float = Field(default=0.5, gt=0, le=1)
    marshal_id: str | None = None
    speech: str | None = Field(default=None, max_length=140)


class MarshalRedirect:
    type = "marshal_redirect"
    label = "Marshal redirect"
    description = (
        "A marshal sends part of the crowd (fraction) heading to from_exit_id, or standing "
        "within radius_m of (x, y), to to_exit_id at at_s."
    )
    params_model = MarshalRedirectEvent

    def validate_refs(self, venue: Venue, p: MarshalRedirectEvent) -> list[str]:
        ids = _exit_ids(venue)
        errs = [] if p.to_exit_id in ids else [f"Unknown exit '{p.to_exit_id}'."]
        if p.from_exit_id and p.from_exit_id not in ids:
            errs.append(f"Unknown exit '{p.from_exit_id}'.")
        return errs

    def tier1_effect(self, state: Tier1State, p: MarshalRedirectEvent) -> None:
        # The Tier 1 solver already balances load across exits; nothing to add.
        return


class OneWayEvent(_E):
    type: Literal["one_way"] = "one_way"
    exit_id: str


class OneWay:
    type = "one_way"
    label = "One-way flow"
    description = "Stewards enforce one-way flow at an exit: nobody can enter against the crowd."
    params_model = OneWayEvent

    def validate_refs(self, venue: Venue, p: OneWayEvent) -> list[str]:
        return [] if p.exit_id in _exit_ids(venue) else [f"Unknown exit '{p.exit_id}'."]

    def tier1_effect(self, state: Tier1State, p: OneWayEvent) -> None:
        ex = state.exits.get(p.exit_id)
        if ex is not None and any("Counterflow at " + p.exit_id in n for n in state.notes):
            ex.capacity_pps /= COUNTERFLOW_CAPACITY_FACTOR  # counterflow is stopped
            state.notes.append(f"One-way flow at {p.exit_id} restores its capacity.")


class ScriptEventModel(_E):
    type: Literal["script"] = "script"
    title: str = Field(min_length=1, max_length=90)
    code: str = Field(min_length=1, max_length=MAX_SCRIPT_CHARS)
    every_s: float = Field(default=1.0, ge=0.25, le=600)

    @field_validator("code")
    @classmethod
    def _static_check(cls, code: str) -> str:
        # static only: the API never runs script code (it runs inside the sim sandbox)
        problems = check_script(code)
        if problems:
            raise ValueError("; ".join(problems))
        return code


class Script:
    type = "script"
    label = "AI-written scenario"
    description = (
        "Python code with on_step(view, act), called every every_s seconds of simulated "
        "time from at_s inside the simulation sandbox."
    )
    params_model = ScriptEventModel

    def validate_refs(self, venue: Venue, p: ScriptEventModel) -> list[str]:
        # ids are read at run time; unknown ones become run notes, never errors
        return []

    def tier1_effect(self, state: Tier1State, p: ScriptEventModel) -> None:
        state.notes.append(
            f"The instant estimate cannot run the scenario script “{p.title}”; "
            "only a simulation shows its effect."
        )


ALL_EVENTS = [
    BlockExit(),
    UnblockExit(),
    Surge(),
    Slowdown(),
    Counterflow(),
    StaggeredRelease(),
    MarshalRedirect(),
    OneWay(),
    Script(),
]


def showtime_register(registry: Registry, config: Config) -> None:
    """Register every built-in scenario event."""
    for ev in ALL_EVENTS:
        registry.add("ScenarioEvent", ev.type, ev)
