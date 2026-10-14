"""Pydantic contracts shared by the API, plugins and (as JSON) the sim image and web UI."""

from api.models.run import (
    Hotspot,
    PerExit,
    ResultBasis,
    RunArtifacts,
    RunMetrics,
    RunRequest,
    RunResult,
    RunStatus,
    result_basis,
)
from api.models.scenario import (
    Attack,
    Fix,
    InspiredBy,
    PatchOpIn,
    ScenarioEventIn,
    VenuePatch,
)
from api.models.session import ApiError, Countdown, SessionEvent, SessionEventType, Usage
from api.models.venue import (
    Exit,
    Floor,
    Location,
    Obstacle,
    Point,
    Polygon,
    StageParams,
    Stair,
    Venue,
    Zone,
)

__all__ = [
    "ApiError",
    "Attack",
    "Countdown",
    "Exit",
    "Fix",
    "Floor",
    "Hotspot",
    "InspiredBy",
    "Location",
    "Obstacle",
    "PatchOpIn",
    "PerExit",
    "Point",
    "Polygon",
    "ResultBasis",
    "RunArtifacts",
    "RunMetrics",
    "RunRequest",
    "RunResult",
    "RunStatus",
    "ScenarioEventIn",
    "SessionEvent",
    "SessionEventType",
    "StageParams",
    "Stair",
    "Usage",
    "Venue",
    "VenuePatch",
    "Zone",
    "result_basis",
]

# Resolve typed planning fields after both sides of the scene/plan contract load.
from api.models.plan import ObjectConstraint, PlanAction

Fix.model_rebuild(_types_namespace={"PlanAction": PlanAction, "ObjectConstraint": ObjectConstraint})
