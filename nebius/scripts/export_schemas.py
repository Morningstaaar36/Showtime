"""Export JSON Schema for the API contracts (consumed by `make types` -> web/src/types/generated.ts)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pydantic.json_schema import models_json_schema

from api.core.countdown import Countdown
from api.core.extensions import HazardResult, IncidentRecord, ReportBundle, RuleFinding
from api.core.geometry import Check, ValidationReport
from api.models import (
    ApiError,
    Attack,
    Fix,
    PatchOpIn,
    RunRequest,
    RunResult,
    SessionEvent,
    StageParams,
    Usage,
    Venue,
    VenuePatch,
)
from plugins.hazard_wind.stage_check import StageCheckResult

MODELS = [
    Venue,
    VenuePatch,
    PatchOpIn,
    StageParams,
    Attack,
    Fix,
    RunRequest,
    RunResult,
    SessionEvent,
    Countdown,
    Usage,
    ApiError,
    HazardResult,
    Check,
    ValidationReport,
    StageCheckResult,
    RuleFinding,
    IncidentRecord,
    ReportBundle,
]


def main(out: Path) -> None:
    _, schema = models_json_schema(
        [(m, "serialization") for m in MODELS], ref_template="#/definitions/{model}"
    )
    combined = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "ShowtimeContracts",
        "type": "object",
        "definitions": schema.get("$defs", {}),
        "properties": {m.__name__: {"$ref": f"#/definitions/{m.__name__}"} for m in MODELS},
    }
    _normalise(combined)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(combined, indent=1))
    print(f"wrote {out} ({len(combined['definitions'])} definitions)")


def _normalise(node: object) -> None:
    """Make the schema friendly to json-schema-to-typescript (draft-07).

    Responses always contain every field, so all properties become required; tuples
    (`prefixItems`) become draft-07 `items` arrays.
    """
    if isinstance(node, dict):
        if "prefixItems" in node:
            node["items"] = node.pop("prefixItems")
            node["minItems"] = node["maxItems"] = len(node["items"])
        if node.get("type") == "object" and "properties" in node:
            node["required"] = sorted(node["properties"])
        for v in node.values():
            _normalise(v)
    elif isinstance(node, list):
        for v in node:
            _normalise(v)


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "web/src/types/contracts.schema.json"))
