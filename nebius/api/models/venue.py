"""Venue contract (section 6.1). All units are metres and seconds."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SCHEMA_VERSION = 1

Point = tuple[float, float]
Polygon = list[Point]

ObstacleKind = Literal[
    "stage", "wall", "barrier", "fence", "booth", "seating", "column", "bar", "other"
]

# What kind of event or building this is; sets behaviour defaults (speeds, pre-movement,
# which incidents the red team draws on). None means "not said" (generic crowd).
EventKind = Literal[
    "concert",
    "festival",
    "conference",
    "wedding",
    "rally",
    "march",
    "sports",
    "religious",
    "hospital",
    "school",
    "office",
    "mall",
    "transit",
    "residential",
    "airport",
    "market",
    "campus",
    "other",
]

# People who move differently from a general adult crowd. Speeds per kind are sim defaults
# documented in docs/ASSUMPTIONS.md; "bed" and "wheelchair" need staff help to move.
PeopleKind = Literal["general", "elderly", "child", "wheelchair", "bed", "staff"]


def _check_polygon(poly: list[Point], what: str) -> list[Point]:
    if len(poly) < 3:
        raise ValueError(f"{what} needs at least 3 points")
    return [(round(float(x), 4), round(float(y), 4)) for x, y in poly]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Obstacle(_Strict):
    """A non-walkable area on a floor (stage, wall segment, barrier, ...)."""

    id: str
    kind: ObstacleKind = "other"
    polygon: Polygon
    height_m: float | None = None
    label: str | None = None
    line: list[Point] | None = None  # centreline for barriers drawn as lines

    @field_validator("polygon")
    @classmethod
    def check_polygon(cls, v: list[Point]) -> list[Point]:
        return _check_polygon(v, "obstacle")


class Exit(_Strict):
    """An exit area placed just inside the walkable boundary."""

    id: str
    polygon: Polygon
    width_m: float = Field(gt=0, le=50)
    blocked: bool = False
    label: str | None = None

    @field_validator("polygon")
    @classmethod
    def check_polygon(cls, v: list[Point]) -> list[Point]:
        return _check_polygon(v, "exit")


class PeopleGroup(_Strict):
    """A share of a zone's headcount that moves differently; the rest are "general"."""

    kind: PeopleKind
    share: float = Field(gt=0, le=1)


class Zone(_Strict):
    """A starting area with a headcount."""

    id: str
    polygon: Polygon
    people: int = Field(ge=0, le=100_000)
    label: str | None = None
    groups: list[PeopleGroup] = Field(default_factory=list)
    # seconds before people here start moving (alarm to first step); None = the run default
    pre_movement_s: float | None = Field(default=None, ge=0, le=1800)
    # people walk this route (a march or procession) before heading to an exit
    route_id: str | None = None
    # people here head for these exits only (where they were going); empty = the best exit
    exit_ids: list[str] = Field(default_factory=list)

    @field_validator("polygon")
    @classmethod
    def check_polygon(cls, v: list[Point]) -> list[Point]:
        return _check_polygon(v, "zone")

    @field_validator("groups")
    @classmethod
    def check_groups(cls, v: list[PeopleGroup]) -> list[PeopleGroup]:
        if sum(g.share for g in v) > 1.0 + 1e-6:
            raise ValueError("people group shares add up to more than 100%")
        if len({g.kind for g in v}) != len(v):
            raise ValueError("each people group kind may appear once per zone")
        return v


class Floor(_Strict):
    """One storey (or the ground of an open-air site)."""

    floor_id: str
    name: str | None = None
    elevation_m: float = 0.0
    walkable: Polygon
    obstacles: list[Obstacle] = Field(default_factory=list)
    exits: list[Exit] = Field(default_factory=list)
    zones: list[Zone] = Field(default_factory=list)

    @field_validator("walkable")
    @classmethod
    def check_walkable(cls, v: list[Point]) -> list[Point]:
        return _check_polygon(v, "walkable area")


class Stair(_Strict):
    """A stair connecting an upper floor (top) to a lower floor (bottom)."""

    id: str
    from_floor: str
    to_floor: str
    top_polygon: Polygon
    bottom_polygon: Polygon
    width_m: float = Field(gt=0)
    length_m: float = Field(gt=0)


class Route(_Strict):
    """A walking route on one floor (a march, a procession, a queue line), in walking order."""

    id: str
    floor_id: str
    points: list[Point] = Field(min_length=2)
    width_m: float | None = Field(default=None, gt=0, le=100)
    label: str | None = None

    @field_validator("points")
    @classmethod
    def check_points(cls, v: list[Point]) -> list[Point]:
        return [(round(float(x), 4), round(float(y), 4)) for x, y in v]


class StageParams(_Strict):
    """Temporary stage structure used by the wind screening check."""

    width_m: float = Field(gt=0)
    depth_m: float = Field(gt=0)
    roof_height_m: float = Field(gt=0)
    roof_area_m2: float = Field(gt=0)
    legs: int = Field(ge=4, le=24)
    ballast_kg_per_leg: float = Field(ge=0)
    friction_coeff: float = Field(gt=0, le=1.5)
    force_coeff: float = Field(gt=0, le=3)
    banner_area_m2: float = Field(default=0.0, ge=0)


class Location(_Strict):
    """Where and when the event happens."""

    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    timezone: str = "UTC"
    event_start: str | None = None  # local ISO datetime


class Venue(_Strict):
    """The single source of truth for a venue; edited only through patches."""

    schema_version: int = SCHEMA_VERSION
    venue_id: str
    name: str
    description: str | None = None
    mode: Literal["indoor", "outdoor"]
    event_kind: EventKind | None = None
    floors: list[Floor] = Field(min_length=1)
    stairs: list[Stair] = Field(default_factory=list)
    routes: list[Route] = Field(default_factory=list)
    stage: StageParams | None = None
    location: Location | None = None
    rules_profile: str = "default"
    extensions: dict[str, Any] = Field(default_factory=dict)

    def floor(self, floor_id: str) -> Floor:
        """Return a floor by id or raise KeyError."""
        for f in self.floors:
            if f.floor_id == floor_id:
                return f
        raise KeyError(floor_id)

    def total_people(self) -> int:
        """Sum of all zone headcounts."""
        return sum(z.people for f in self.floors for z in f.zones)

    def all_ids(self) -> dict[str, str]:
        """Map of every object id to its kind (for agent validators)."""
        out: dict[str, str] = {}
        for f in self.floors:
            out[f.floor_id] = "floor"
            for o in f.obstacles:
                out[o.id] = "obstacle"
            for e in f.exits:
                out[e.id] = "exit"
            for z in f.zones:
                out[z.id] = "zone"
        for s in self.stairs:
            out[s.id] = "stair"
        for r in self.routes:
            out[r.id] = "route"
        return out
