"""VenueSpec: a venue described by relationships, not coordinates.

The designer agent writes this; `api.core.venue_builder` turns it into a `Venue` with exact
geometry. Language models place objects badly when they write coordinates (LayoutGPT,
LayoutVLM), so the model only chooses sizes, walls and regions and a solver does the rest
(the Holodeck / Text2BIM pattern: describe → solve → check → repair).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Wall = Literal["north", "south", "east", "west"]
Region = Literal[
    "whole",
    "centre",
    "front",
    "middle",
    "back",
    "left",
    "right",
    "front_left",
    "front_right",
    "back_left",
    "back_right",
]
FeatureKind = Literal[
    "bar",
    "booth",
    "sound_desk",
    "toilets",
    "seating",
    "column",
    "tent",
    "barrier",
    "escalator",
    "other",
]
BuildingUse = Literal[
    "office",
    "hospital",
    "school",
    "mall",
    "residential",
    "transit",
    "religious",
    "conference",
    "concert",
    "sports",
    "other",
]
StairPlace = Literal["north", "south", "east", "west", "centre"]

_CENTRE = {"center", "centre", "central", "in the centre", "in the center"}


def _centre(v: object, *also: str) -> object:
    """'center', 'central' and the like (and any of `also`) all mean the centre."""
    if isinstance(v, str) and v.strip().lower() in _CENTRE.union(also):
        return "centre"
    return v


class _Spec(BaseModel):
    model_config = ConfigDict(extra="ignore")


class StageSpec(_Spec):
    """A stage against one wall, centred on it, or free-standing in the centre."""

    wall: Wall | Literal["centre"] = "north"
    width_m: float = Field(default=12, ge=2, le=80)
    depth_m: float = Field(default=6, ge=1, le=30)
    roof_height_m: float = Field(default=10, ge=2, le=40)

    @field_validator("wall", mode="before")
    @classmethod
    def _wall(cls, v: object) -> object:
        return _centre(v, "middle")


class ExitSpec(_Spec):
    """An exit on a wall; `position` runs 0..1 from the west end (or south end) of the wall.

    `level` is the storey (0 = street level, 1 = first floor, -1 = basement). An exit on a
    basement is a stair up to a street door on the same wall.
    """

    wall: Wall
    width_m: float = Field(default=2.0, ge=0.8, le=20)
    position: float = Field(default=0.5, ge=0, le=1)
    label: str | None = Field(default=None, max_length=40)
    level: int = Field(default=0, ge=-3, le=39)


class ZoneSpec(_Spec):
    """People standing or seated in a region. Front is the side nearest the stage."""

    label: str = Field(default="Audience", max_length=40)
    people: int = Field(ge=0, le=20_000)
    region: Region = "whole"


class FeatureSpec(_Spec):
    """An obstacle placed in a region or against a wall."""

    kind: FeatureKind = "other"
    label: str | None = Field(default=None, max_length=40)
    place: Region | Wall = "middle"
    width_m: float = Field(default=4, ge=0.5, le=60)
    depth_m: float = Field(default=3, ge=0.5, le=40)
    level: int | None = Field(
        default=None, ge=-3, le=39, description="storey; null = street level (escalators: all)"
    )

    @field_validator("place", mode="before")
    @classmethod
    def _place(cls, v: object) -> object:
        return _centre(v)


class UpperFloorSpec(_Spec):
    """A balcony or mezzanine along the north or south wall, reached by one stair."""

    along: Literal["north", "south"] = "north"
    depth_m: float = Field(default=8, ge=3, le=60)
    people: int = Field(default=200, ge=0, le=10_000)
    label: str = Field(default="Balcony", max_length=40)
    stair_end: Literal["east", "west"] = "east"
    stair_width_m: float = Field(default=2.0, ge=1, le=6)


class StairCoreSpec(_Spec):
    """A stair core joining every storey, near one wall (or in the centre)."""

    place: StairPlace = "east"
    width_m: float = Field(default=1.2, ge=0.8, le=4, description="flight width")

    @field_validator("place", mode="before")
    @classmethod
    def _place(cls, v: object) -> object:
        return _centre(v, "middle")


class LevelSpec(_Spec):
    """One level of a building whose headcount or name differs from the others."""

    level: int = Field(ge=-3, le=39, description="0 = street level, 1 = first floor, -1 = basement")
    people: int = Field(default=0, ge=0, le=20_000)
    name: str | None = Field(default=None, max_length=30, description="'Lobby', 'Platform'")


class BuildingSpec(_Spec):
    """A building with several storeys (and basements), built floor by floor by the solver."""

    storeys: int = Field(default=1, ge=1, le=40, description="levels from street level up")
    basements: int = Field(default=0, ge=0, le=3, description="levels below street level")
    use: BuildingUse | None = None
    interior: Literal["open", "rooms", "atrium"] = "open"
    rooms_per_floor: int | None = Field(default=None, ge=2, le=60)
    room_label: str | None = Field(default=None, max_length=30, description="'Guest room', 'Ward'")
    people_per_floor: int | None = Field(
        default=None, ge=0, le=20_000, description="headcount on every level not in `levels`"
    )
    levels: list[LevelSpec] = Field(default_factory=list, max_length=43)
    stairs: list[StairCoreSpec] = Field(default_factory=list, max_length=6)
    floor_height_m: float = Field(default=3.5, ge=2.5, le=8)

    @property
    def level_numbers(self) -> list[int]:
        """Every level, lowest first (basements are negative, street level is 0)."""
        return list(range(-self.basements, self.storeys))


UPPER_WORDS = ("balcony", "mezzanine", "gallery", "upper", "first floor", "level 1")


class VenueSpec(_Spec):
    """Everything the builder needs. Sizes in metres; x runs east, y runs north."""

    name: str = Field(default="New venue", max_length=80)
    mode: Literal["indoor", "outdoor"] = "indoor"
    width_m: float = Field(ge=6, le=400, description="east-west size")
    depth_m: float = Field(ge=6, le=400, description="north-south size")
    stage: StageSpec | None = None
    front_barrier: bool = False
    exits: list[ExitSpec] = Field(min_length=1, max_length=16)
    zones: list[ZoneSpec] = Field(default_factory=list, max_length=8)
    features: list[FeatureSpec] = Field(default_factory=list, max_length=12)
    upper_floor: UpperFloorSpec | None = None
    building: BuildingSpec | None = None
    location: str | None = Field(default=None, max_length=80, description="city or place name")
    assumptions: list[str] = Field(default_factory=list, max_length=6)

    @field_validator("assumptions", mode="before")
    @classmethod
    def _few(cls, v: object) -> object:
        return v[:6] if isinstance(v, list) else v

    def level_people(self) -> list[int] | None:
        """Headcount per level, lowest first, as the spec states it (None: not stated per level).

        A one-level venue counts its zones and balcony instead (see `total_people`).
        """
        b = self.building
        if b is None or (b.people_per_floor is None and not b.levels):
            return None
        given = {lv.level: lv.people for lv in b.levels}
        return [given.get(k, b.people_per_floor or 0) for k in b.level_numbers]

    def ground_zones(self) -> list[ZoneSpec]:
        """Zones on the main floor: with a balcony, zones named after it are the balcony."""
        if self.upper_floor is None:
            return list(self.zones)
        return [z for z in self.zones if not any(w in z.label.lower() for w in UPPER_WORDS)]

    def total_people(self) -> int:
        """Everyone the spec places: per-level counts for a building, else zones and balcony."""
        per = self.level_people()
        if per is not None:
            return sum(per)
        up = self.upper_floor.people if self.upper_floor is not None else 0
        return sum(z.people for z in self.ground_zones()) + up


class EventBrief(_Spec):
    """What the organizer asked for, read from one sentence (the Event Copilot's first step)."""

    title: str = Field(default="New event", max_length=80)
    kind: str = Field(default="event", max_length=40, description="concert, conference, wedding …")
    place: str | None = Field(
        default=None, max_length=120, description="a real place or address to look up, else null"
    )
    setting: Literal["indoor", "outdoor"] = "outdoor"
    attendees: int = Field(ge=10, le=100_000)
    start: str | None = Field(
        default=None, max_length=25, description="local ISO date-time or null"
    )
    duration_h: float = Field(default=4, gt=0, le=72)
    alcohol: bool = False
    audience: Literal["standing", "seated", "mixed"] = "standing"
    stage: bool = True
    layout: str = Field(
        default="",
        max_length=600,
        description="if no real place: the venue in words (size, doors, stage) for the designer",
    )
    assumptions: list[str] = Field(default_factory=list, max_length=6)
