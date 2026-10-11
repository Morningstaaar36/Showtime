"""Versioned scene snapshots and computed spatial facts; no simulator output."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from api.models.venue import Point, Polygon, Venue

SceneObjectKind = Literal["floor", "obstacle", "exit", "zone", "stair"]
ZoneReachability = Literal["reachable", "partially_reachable", "unreachable", "unplaced"]
ZonePlacement = Literal["fully_placed", "partially_placed", "unplaced"]


class SceneModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class InputProvenance(SceneModel):
    basis: Literal["unknown", "assumed", "imported", "organizer_confirmed", "measured"] = "unknown"
    source: str | None = None
    recorded_at: datetime | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def measured_source(self) -> InputProvenance:
        if self.basis == "measured" and not (self.source and self.source.strip()):
            raise ValueError("Measured inputs require a supplied measurement source.")
        return self


class SceneMetadata(SceneModel):
    """Optional venue.extensions.scene_metadata; missing provenance stays unknown."""

    schema_version: Literal[1] = 1
    objects: dict[str, InputProvenance] = Field(default_factory=dict)
    fields: dict[str, dict[str, InputProvenance]] = Field(default_factory=dict)


class SceneUnits(SceneModel):
    coordinates: Literal["m"] = "m"
    elevation: Literal["m"] = "m"
    area: Literal["m2"] = "m2"
    distance: Literal["m"] = "m"
    time: Literal["s"] = "s"
    coordinate_system: Literal["local_cartesian"] = "local_cartesian"


class SceneIdentity(SceneModel):
    project_id: str | None = None
    venue_id: str
    venue_version: int | None = None
    venue_schema_version: int
    venue_hash: str
    scene_hash: str


class SceneObject(SceneModel):
    id: str
    kind: SceneObjectKind
    floor_id: str | None = None
    provenance: InputProvenance = Field(default_factory=InputProvenance)
    fields: dict[str, InputProvenance] = Field(default_factory=dict)


class SceneSnapshot(SceneModel):
    schema_version: Literal[1] = 1
    identity: SceneIdentity
    units: SceneUnits = Field(default_factory=SceneUnits)
    venue: Venue
    objects: list[SceneObject]
    metadata: SceneMetadata


class SpatialIssue(SceneModel):
    code: str
    severity: Literal["error", "warning", "info"]
    message: str
    target_ids: list[str] = Field(default_factory=list)
    floor_id: str | None = None


class PolygonSurface(SceneModel):
    exterior: Polygon
    holes: list[Polygon] = Field(default_factory=list)


class ComponentFacts(SceneModel):
    component_id: str
    floor_id: str
    area_m2: float
    geometry: PolygonSurface
    representative_point: Point
    direct_exit_ids: list[str]
    reachable_exit_ids: list[str]
    downstream_component_ids: list[str]


class ExitFacts(SceneModel):
    exit_id: str
    floor_id: str
    blocked: bool
    available_in_geometry: bool
    declared_width_m: float
    usable_area_m2: float
    usable_area_fraction: float
    component_ids: list[str]
    nearest_obstacle_distance_m: float | None


class StairFacts(SceneModel):
    stair_id: str
    from_floor: str
    to_floor: str
    from_component_ids: list[str]
    to_component_ids: list[str]
    connected: bool
    declared_width_m: float
    declared_length_m: float
    direction: Literal["from_floor_to_to_floor"] = "from_floor_to_to_floor"


class RouteFacts(SceneModel):
    status: Literal["computed", "unreachable", "not_computed"]
    exit_id: str | None = None
    distance_m: float | None = None
    waypoint_count: int = 0
    reason: str | None = None
    basis: Literal["polygon_visibility_graph"] = "polygon_visibility_graph"


class ZonePartFacts(SceneModel):
    component_id: str
    usable_area_m2: float
    fraction_of_usable_zone_area: float
    representative_point: Point
    point_clearance_m: float
    reachable_exit_ids: list[str]
    route: RouteFacts


class ZoneFacts(SceneModel):
    zone_id: str
    floor_id: str
    people: int
    usable_area_m2: float
    excluded_area_m2: float
    reachable_area_m2: float
    unreachable_area_m2: float
    placement: ZonePlacement
    reachability: ZoneReachability
    reachable_exit_ids: list[str]
    parts: list[ZonePartFacts]


class FloorFacts(SceneModel):
    floor_id: str
    elevation_m: float
    walkable_area_m2: float
    obstacle_area_within_floor_m2: float
    usable_area_m2: float
    component_ids: list[str]


class SceneFacts(SceneModel):
    schema_version: Literal[1] = 1
    identity: SceneIdentity
    units: SceneUnits = Field(default_factory=SceneUnits)
    basis: Literal["computed_geometry"] = "computed_geometry"
    floors: list[FloorFacts]
    components: list[ComponentFacts]
    exits: list[ExitFacts]
    stairs: list[StairFacts]
    zones: list[ZoneFacts]
    issues: list[SpatialIssue]
    routes_computed: bool
    route_budget_reason: str | None = None
    limitations: list[str]
