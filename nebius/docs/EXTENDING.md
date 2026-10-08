# Extending Showtime

Every feature is a plugin. A plugin is a folder `plugins/<id>/` with a `plugin.toml` manifest, an
`__init__.py` that defines `Config` (Pydantic) and `showtime_register(registry, config)`, and
tests. Plugins import only `api.core.extensions` and `api.models` (enforced by `make lint`).

```bash
make new-plugin TYPE=HazardSource ID=hazard_flood   # scaffold + test file
make plugins                                        # list plugins and health
FEATURE_HAZARD_FLOOD=false make dev                 # turn a plugin off
```

## Add a hazard in 5 steps (example: flooded corridor)
1. `make new-plugin TYPE=HazardSource ID=hazard_flood`.
2. Implement a class with `id`, `label`, `modes = ("indoor",)` and
   `async def evaluate(self, ctx: HazardContext) -> HazardResult | None`. Return the time (s
   after the alarm) when a route becomes unusable and an explanation; return `None` when it
   does not apply. Never invent numbers: compute them or read them from a provider.
3. Register it: `registry.add("HazardSource", "hazard_flood", FloodHazard(config))`.
4. Test it with `check_hazard_source` from `api/tests/conformance/suites.py`.
5. Add any default values to `docs/ASSUMPTIONS.md`. The countdown picks the earliest hazard.

## Recipes per extension point

| Extension point | Implement | Register as | Conformance |
| --- | --- | --- | --- |
| `PatchOp` (edit) | `name`, `description`, `params_model` (with `op: Literal[...]`), `validate`, `apply` (pure), `invert` | `registry.add("PatchOp", name, op)` | `check_patch_op` (applies, validates, undoes exactly) |
| `ScenarioEvent` | `type`, `label`, `description`, `params_model`, `validate_refs`, `tier1_effect`; plus a handler in `sim/plugins/events.py` | `"ScenarioEvent"` | `check_scenario_event` |
| `HazardSource` | `evaluate(ctx)` | `"HazardSource"` | `check_hazard_source` |
| `RulesPack` | `check(venue, tier1) -> list[RuleFinding]` with `source_url` | `"RulesPack"` | — |
| `IncidentSource` | `search(features, limit)`, `count()`; every record needs `source_url` | `"IncidentSource"` | — |
| `Exporter` | `id`, `label`, `media_type`, `file_ext`, `render(bundle) -> bytes` (include the disclaimer) | `"Exporter"` | `check_exporter` |
| `VenueImporter` | `file_extensions`, `import_bytes(data, filename) -> Venue` (raise `ValueError` with a readable message) | `"VenueImporter"` | — |
| `SimEngine` | a module in `sim/plugins/` with `run(...)`, listed in `sim/plugins/registry.json`; rebuild the image | — | `sim/tests` |
| Lifecycle hooks | `on_venue_changed`, `on_run_started`, `on_run_finished`, `on_session_event`, `on_session_finished` as module functions | automatic (pluggy) | — |
| Routes | `register_routes(plugin_id)` returning a FastAPI `APIRouter` (mounted at `/api/v1/plugins/<id>/`) | automatic | — |

## Frontend extensions
UI plugins live in `web/src/plugins/<id>/` and are picked up with `import.meta.glob`; panels and
3D layers read `/api/v1/features` and render only what is enabled.

## Contracts grow additively
Every contract has `schema_version` and an `extensions: {}` object for plugin data under the
plugin's id. Renaming or removing a field needs a version bump and a migration.
