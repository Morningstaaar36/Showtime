"""Plugin SDK: extension-point protocols, the registry and hook markers.

Plugins may import only from `api.core.extensions` and `api.models` (enforced by
import-linter in `make check`).
"""

from api.core.extensions import geometry
from api.core.extensions.protocols import (
    API_VERSION,
    AgentSpec,
    Exporter,
    HazardContext,
    HazardResult,
    HazardSource,
    IncidentRecord,
    IncidentSource,
    Metric,
    PatchOp,
    Provider,
    ReportBundle,
    RuleFinding,
    RulesPack,
    ScenarioEvent,
    SimEngine,
    T1Exit,
    T1Group,
    Tier1State,
    Tool,
    VenueImporter,
)
from api.core.extensions.registry import (
    EXTENSION_POINTS,
    HookSpecs,
    Registered,
    Registry,
    hookimpl,
    hookspec,
)

__all__ = [
    "API_VERSION",
    "EXTENSION_POINTS",
    "AgentSpec",
    "Exporter",
    "HazardContext",
    "HazardResult",
    "HazardSource",
    "HookSpecs",
    "IncidentRecord",
    "IncidentSource",
    "Metric",
    "PatchOp",
    "Provider",
    "Registered",
    "Registry",
    "ReportBundle",
    "RuleFinding",
    "RulesPack",
    "ScenarioEvent",
    "SimEngine",
    "T1Exit",
    "T1Group",
    "Tier1State",
    "Tool",
    "VenueImporter",
    "geometry",
    "hookimpl",
    "hookspec",
]
