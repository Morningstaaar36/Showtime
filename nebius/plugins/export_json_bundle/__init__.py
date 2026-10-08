"""Exporter: the full report bundle as JSON (for archives and other tools)."""

from __future__ import annotations

from pydantic import BaseModel

from api.core.extensions import Registry, ReportBundle


class Config(BaseModel):
    """No settings."""


class JsonBundleExporter:
    """Everything behind the report, machine-readable."""

    id = "export_json_bundle"
    label = "Data bundle (JSON)"
    media_type = "application/json"
    file_ext = "json"

    def render(self, bundle: ReportBundle) -> bytes:
        return bundle.model_dump_json(indent=1, exclude={"extras"}).encode()


def showtime_register(registry: Registry, config: Config) -> None:
    """Register the exporter."""
    registry.add("Exporter", JsonBundleExporter.id, JsonBundleExporter())
