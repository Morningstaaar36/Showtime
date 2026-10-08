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


class Zone(_Strict):
    """A starting area with a headcount."""

    id: str
    polygon: Polygon
    people: int = Field(ge=0, le=100_000)
    label: str | None = None

    @field_validator("polygon")
    @classmethod
    def check_polygon(cls, v: list[Point]) -> list[Point]:
        return _check_polygon(v, "zone")


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
    floors: list[Floor] = Field(min_length=1)
    stairs: list[Stair] = Field(default_factory=list)
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
        return out
