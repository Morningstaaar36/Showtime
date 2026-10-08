"""VenueImporter for Showtime venue JSON files."""

from __future__ import annotations

import json

from pydantic import BaseModel, ValidationError

from api.core.extensions import Registry
from api.models import Venue


class Config(BaseModel):
    """No settings."""


class JsonImporter:
    id = "import_json"
    label = "Venue JSON"
    file_extensions = (".json",)

    def import_bytes(self, data: bytes, filename: str) -> Venue:
        try:
            return Venue.model_validate(json.loads(data))
        except (json.JSONDecodeError, ValidationError) as exc:
            msg = str(exc).splitlines()[0][:200]
            raise ValueError(f"{filename} is not a valid Showtime venue: {msg}") from exc


def showtime_register(registry: Registry, config: Config) -> None:
    registry.add("VenueImporter", JsonImporter.id, JsonImporter())
