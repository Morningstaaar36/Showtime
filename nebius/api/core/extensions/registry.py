"""Registries for every extension point, plus pluggy hook specifications."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pluggy

from api.core.extensions.protocols import (
    AgentSpec,
    Exporter,
    HazardSource,
    IncidentSource,
    Metric,
    PatchOp,
    Provider,
    RulesPack,
    ScenarioEvent,
    SimEngine,
    Tool,
    VenueImporter,
)

PROJECT = "showtime"
hookspec = pluggy.HookspecMarker(PROJECT)
hookimpl = pluggy.HookimplMarker(PROJECT)

EXTENSION_POINTS: dict[str, type] = {
    "VenueImporter": VenueImporter,
    "PatchOp": PatchOp,
    "ScenarioEvent": ScenarioEvent,
    "SimEngine": SimEngine,
    "Metric": Metric,
    "HazardSource": HazardSource,
    "RulesPack": RulesPack,
    "IncidentSource": IncidentSource,
    "Agent": AgentSpec,
    "Tool": Tool,
    "Provider": Provider,
    "Exporter": Exporter,
}


@dataclass
class Registered:
    """An object registered at an extension point, with the plugin that owns it."""

    point: str
    key: str
    obj: Any
    plugin_id: str


@dataclass
class Registry:
    """Holds every registered extension, keyed by extension point and key."""

    items: dict[str, dict[str, Registered]] = field(default_factory=dict)
    _current_plugin: str = "core"

    def add(self, point: str, key: str, obj: Any) -> None:
        """Register `obj` at `point` under `key`. The object must satisfy the protocol."""
        proto = EXTENSION_POINTS.get(point)
        if proto is None:
            raise ValueError(f"unknown extension point {point!r}")
        if not isinstance(obj, proto):
            raise TypeError(f"{key!r} does not implement {point}")
        bucket = self.items.setdefault(point, {})
        if key in bucket:
            raise ValueError(f"{point} {key!r} already registered by {bucket[key].plugin_id}")
        bucket[key] = Registered(point, key, obj, self._current_plugin)

    def get(self, point: str, key: str) -> Any:
        """Look up an extension; raises KeyError with the list of known keys."""
        bucket = self.items.get(point, {})
        if key not in bucket:
            raise KeyError(f"no {point} named {key!r}; known: {sorted(bucket)}")
        return bucket[key].obj

    def has(self, point: str, key: str) -> bool:
        """True if registered."""
        return key in self.items.get(point, {})

    def all(self, point: str) -> list[Any]:
        """All objects at an extension point, in registration order."""
        return [r.obj for r in self.items.get(point, {}).values()]

    def keys(self, point: str) -> list[str]:
        """Keys registered at an extension point."""
        return list(self.items.get(point, {}))

    def owned_by(self, plugin_id: str) -> list[Registered]:
        """Everything a plugin registered."""
        return [r for b in self.items.values() for r in b.values() if r.plugin_id == plugin_id]

    def remove_plugin(self, plugin_id: str) -> None:
        """Drop everything a failed plugin registered."""
        for bucket in self.items.values():
            for key in [k for k, r in bucket.items() if r.plugin_id == plugin_id]:
                del bucket[key]

    def as_plugin(self, plugin_id: str) -> _PluginScope:
        """Context manager attributing registrations to a plugin."""
        return _PluginScope(self, plugin_id)

    # Typed helpers ------------------------------------------------------
    def patch_op(self, name: str) -> PatchOp:
        """Patch op by name."""
        return self.get("PatchOp", name)  # type: ignore[no-any-return]

    def event(self, type_: str) -> ScenarioEvent:
        """Scenario event by type."""
        return self.get("ScenarioEvent", type_)  # type: ignore[no-any-return]


class _PluginScope:
    def __init__(self, reg: Registry, plugin_id: str) -> None:
        self.reg = reg
        self.plugin_id = plugin_id
        self.prev = reg._current_plugin

    def __enter__(self) -> Registry:
        self.reg._current_plugin = self.plugin_id
        return self.reg

    def __exit__(self, *exc: object) -> None:
        self.reg._current_plugin = self.prev


class HookSpecs:
    """Lifecycle hooks plugins may implement (all optional)."""

    @hookspec
    def showtime_register(self, registry: Registry, config: Any) -> None:
        """Register extensions. Called once at startup for each enabled plugin."""

    @hookspec
    def on_venue_changed(self, project_id: str, venue: Any, version: int) -> None:
        """A new venue version was saved."""

    @hookspec
    def on_run_started(self, request: Any) -> None:
        """A simulation run started."""

    @hookspec
    def on_run_finished(self, result: Any) -> None:
        """A simulation run finished (any status)."""

    @hookspec
    def on_session_event(self, session_id: str, event: Any) -> None:
        """A red-team session emitted an event."""

    @hookspec
    def on_session_finished(self, session_id: str, summary: Any) -> None:
        """A red-team session finished."""

    @hookspec
    def register_routes(self, plugin_id: str) -> Any:
        """Return a FastAPI APIRouter mounted at /api/v1/plugins/<plugin_id>/."""
