"""VenueSpec: a venue described by relationships, not coordinates.

The designer agent writes this; `api.core.venue_builder` turns it into a `Venue` with exact
geometry. Language models place objects badly when they write coordinates (LayoutGPT,
LayoutVLM), so the model only chooses sizes, walls and regions and a solver does the rest
(the Holodeck / Text2BIM pattern: describe → solve → check → repair).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Wall = Literal["north", "south", "east", "west"]
Region = Literal[
    "whole",
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
    "bar", "booth", "sound_desk", "toilets", "seating", "column", "tent", "barrier", "other"
]


class _Spec(BaseModel):
    model_config = ConfigDict(extra="ignore")


class StageSpec(_Spec):
    """A stage against one wall, centred on it."""

    wall: Wall = "north"
    width_m: float = Field(default=12, ge=2, le=80)
    depth_m: float = Field(default=6, ge=1, le=30)
    roof_height_m: float = Field(default=10, ge=2, le=40)


class ExitSpec(_Spec):
    """An exit on a wall; `position` runs 0..1 from the west end (or south end) of the wall."""

    wall: Wall
    width_m: float = Field(default=2.0, ge=0.8, le=20)
    position: float = Field(default=0.5, ge=0, le=1)
    label: str | None = Field(default=None, max_length=40)


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


class UpperFloorSpec(_Spec):
    """A balcony or mezzanine along the north or south wall, reached by one stair."""

    along: Literal["north", "south"] = "north"
    depth_m: float = Field(default=8, ge=3, le=60)
    people: int = Field(default=200, ge=0, le=10_000)
    label: str = Field(default="Balcony", max_length=40)
    stair_end: Literal["east", "west"] = "east"
    stair_width_m: float = Field(default=2.0, ge=1, le=6)


class VenueSpec(_Spec):
    """Everything the builder needs. Sizes in metres; x runs east, y runs north."""

    name: str = Field(default="New venue", max_length=80)
    mode: Literal["indoor", "outdoor"] = "indoor"
    width_m: float = Field(ge=6, le=400, description="east-west size")
    depth_m: float = Field(ge=6, le=400, description="north-south size")
    stage: StageSpec | None = None
    front_barrier: bool = False
    exits: list[ExitSpec] = Field(min_length=1, max_length=16)
    zones: list[ZoneSpec] = Field(min_length=1, max_length=8)
    features: list[FeatureSpec] = Field(default_factory=list, max_length=12)
    upper_floor: UpperFloorSpec | None = None
    location: str | None = Field(default=None, max_length=80, description="city or place name")
    assumptions: list[str] = Field(default_factory=list, max_length=6)


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
