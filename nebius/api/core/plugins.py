"""Plugin discovery and loading (section 7A.2).

Folder plugins live in `plugins/<id>/plugin.toml`; installed packages can register
through the `showtime.plugins` entry-point group. Core never imports a plugin
statically: modules are loaded by name with importlib.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import logging
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pluggy
import yaml
from pydantic import BaseModel, ValidationError

from api.core.extensions import API_VERSION, HookSpecs, Registry
from api.core.extensions.registry import PROJECT

log = logging.getLogger("showtime.plugins")


@dataclass
class PluginStatus:
    """What `make plugins` and `/api/v1/health` report for a plugin."""

    id: str
    name: str
    version: str
    provides: list[str]
    enabled: bool
    healthy: bool
    source: str
    error: str | None = None
    config: dict[str, Any] = field(default_factory=dict)
    registered: list[str] = field(default_factory=list)


@dataclass
class PluginHost:
    """Owns the registry, the pluggy manager and plugin statuses."""

    registry: Registry
    pm: pluggy.PluginManager
    statuses: dict[str, PluginStatus] = field(default_factory=dict)

    def mark_unhealthy(self, plugin_id: str, error: str) -> None:
        """Record a runtime failure; the plugin stays loaded but is reported red."""
        st = self.statuses.get(plugin_id)
        if st:
            st.healthy = False
            st.error = error[:500]

    def enabled_ids(self) -> list[str]:
        """Ids of plugins that loaded."""
        return [s.id for s in self.statuses.values() if s.enabled and s.healthy]


def _feature_flags(root: Path) -> dict[str, bool]:
    path = root / "config" / "features.yaml"
    flags: dict[str, bool] = {}
    if path.exists():
        raw = yaml.safe_load(path.read_text()) or {}
        for k, v in (raw.get("plugins") or {}).items():
            flags[str(k)] = bool(v)
    for key, val in os.environ.items():
        if key.startswith("FEATURE_"):
            flags[key[len("FEATURE_") :].lower()] = val.strip().lower() in (
                "1",
                "true",
                "yes",
                "on",
            )
    return flags


def _load_config(module: Any, manifest_cfg: dict[str, Any]) -> Any:
    model = getattr(module, "Config", None)
    if model is None:
        return manifest_cfg
    if not (isinstance(model, type) and issubclass(model, BaseModel)):
        raise TypeError("plugin Config must be a Pydantic model")
    return model.model_validate(manifest_cfg)


def _register_module(
    host: PluginHost, plugin_id: str, module: Any, config: Any, status: PluginStatus
) -> None:
    try:
        with host.registry.as_plugin(plugin_id):
            fn = getattr(module, "showtime_register", None)
            if fn is not None:
                fn(registry=host.registry, config=config)
        host.pm.register(module, name=plugin_id)
        status.registered = [f"{r.point}:{r.key}" for r in host.registry.owned_by(plugin_id)]
    except Exception as exc:  # isolation: a broken plugin never takes the app down
        host.registry.remove_plugin(plugin_id)
        status.healthy = False
        status.error = f"{type(exc).__name__}: {exc}"[:500]
        log.error("plugin %s failed to register: %s", plugin_id, status.error)


def load_plugins(root: Path, registry: Registry | None = None) -> PluginHost:
    """Discover, configure and register every enabled plugin."""
    pm = pluggy.PluginManager(PROJECT)
    pm.add_hookspecs(HookSpecs)
    host = PluginHost(registry=registry or Registry(), pm=pm)
    flags = _feature_flags(root)

    plugin_dir = root / "plugins"
    for manifest_path in sorted(plugin_dir.glob("*/plugin.toml")):
        if manifest_path.parent.name.startswith("_"):
            continue  # templates and scaffolds
        try:
            manifest = tomllib.loads(manifest_path.read_text())
        except tomllib.TOMLDecodeError as exc:
            log.error("bad manifest %s: %s", manifest_path, exc)
            continue
        meta = manifest.get("plugin", {})
        pid = str(meta.get("id", manifest_path.parent.name))
        status = PluginStatus(
            id=pid,
            name=str(meta.get("name", pid)),
            version=str(meta.get("version", "0")),
            provides=list(meta.get("provides", [])),
            enabled=flags.get(pid, bool(meta.get("enabled_by_default", True))),
            healthy=True,
            source=str(manifest_path.parent.relative_to(root)),
        )
        host.statuses[pid] = status
        if str(meta.get("api_version", "")) != API_VERSION:
            status.healthy = False
            status.error = f"api_version {meta.get('api_version')!r} != {API_VERSION!r}"
            continue
        if not status.enabled:
            continue
        try:
            module = importlib.import_module(f"plugins.{manifest_path.parent.name}")
            config = _load_config(module, dict(manifest.get("config", {})))
        except (ImportError, ValidationError, TypeError) as exc:
            status.healthy = False
            status.error = f"{type(exc).__name__}: {exc}"[:500]
            log.error("plugin %s disabled: %s", pid, status.error)
            continue
        status.config = config.model_dump() if isinstance(config, BaseModel) else dict(config)
        _register_module(host, pid, module, config, status)

    for ep in importlib.metadata.entry_points(group="showtime.plugins"):
        status = PluginStatus(
            id=ep.name,
            name=ep.name,
            version="?",
            provides=[],
            enabled=flags.get(ep.name, True),
            healthy=True,
            source=f"entry point {ep.value}",
        )
        host.statuses[ep.name] = status
        if not status.enabled:
            continue
        try:
            module = ep.load()
            config = _load_config(module, {})
        except Exception as exc:
            status.healthy = False
            status.error = f"{type(exc).__name__}: {exc}"[:500]
            continue
        _register_module(host, ep.name, module, config, status)
    return host


def register_builtin(host: PluginHost, plugin_id: str, name: str, module: Any) -> None:
    """Register an in-tree built-in pack (agents, providers) through the same path."""
    status = PluginStatus(
        id=plugin_id,
        name=name,
        version="0.1.0",
        provides=[],
        enabled=True,
        healthy=True,
        source=module.__name__,
    )
    host.statuses[plugin_id] = status
    _register_module(host, plugin_id, module, {}, status)
    status.provides = sorted({r.point for r in host.registry.owned_by(plugin_id)})
