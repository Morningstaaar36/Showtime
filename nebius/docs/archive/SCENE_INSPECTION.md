# P2-01 — canonical scene and spatial inspection

Implemented on 11 October 2026. The user reported all 29 scene acceptance tests passing,
and the synthetic room's live scene endpoints were checked. The sample and unit fixture
were subsequently corrected for the existing placement-density limit. The corrected
scene suite and existing regressions passed during P2-02 verification on native M1
Python 3.12. The live simulation consistency check remains pending.

## Purpose

Expose the full scene used by the editor/simulator and computed facts that other
components can inspect. This requires no OpenRouter, Nebius, Tavily, or simulation run.
The existing `Venue` remains the source of geometry; this feature does not create a
second CAD or rendering model.

P2-01 supplies the scene contract and read-only geometry tools. Constraints, atomic
agent bundles, operational-plan persistence, evidence invalidation, and agent/UI
integration belong to the subsequent tasks in the team allocation.

## Endpoints

| Request | Response |
| --- | --- |
| `GET /api/v1/projects/{id}/scene` | Typed snapshot with full venue, object index, units, provenance, version, and hashes. |
| `GET /api/v1/projects/{id}/scene?version=1` | The specified saved version, rather than the current one. |
| `GET /api/v1/projects/{id}/scene-facts` | Areas, connected components, exit/stair contacts, zone reachability, representative-point clearances, and bounded routes. |
| `GET /api/v1/projects/{id}/scene-facts?version=1&include_routes=false` | Historical connectivity and areas without building a route graph. |

Unknown projects/versions return the existing `404 not_found` response. Version numbers
below one return `422 invalid_request`. Invalid polygons, duplicate/empty object IDs,
non-finite JSON, unknown stair floors, and invalid provenance return `422 invalid_scene`
with structured issues. The inspection path does not silently repair such geometry.

Blocked or missing exits and unreachable occupied areas are returned as findings in a
successful inspection response; these are meaningful scene conditions, not malformed
JSON. Snapshot and facts include the same source identity.

## Identity and geometry

- `venue` retains every floor polygon, obstacle, exit, zone, stair landing, dimension,
  elevation, location, stage parameter, and extension in the saved `Venue`.
- `objects` identifies existing floors, obstacles, exits, zones, and stairs by their
  supplied IDs. IDs must be unique within the venue. No importer or template rewrite
  is required.
- Coordinates/elevations/distances are metres; areas are square metres; time is seconds.
  Coordinates are local Cartesian, not latitude/longitude. Event location remains a
  separate existing venue field.
- `identity.venue_version` identifies the saved version. Undo also creates a new version.
- `identity.venue_hash` retains the existing simulation-layout hash for compatibility.
- `identity.scene_hash` hashes the complete saved venue JSON, including provenance and
  extensions. This prevents metadata-only changes from appearing identical to a model
  consumer. It does not replace simulation cache identity in P2-03.
- Component IDs are derived and stable for the same geometry, not permanent building
  object IDs. Always interpret them with the source scene identity.
- Component geometry contains exterior rings and holes. Overlapping obstacles are
  subtracted as a union rather than counted twice.

## Provenance

Optional typed metadata is read from `venue.extensions.scene_metadata`. Existing
projects without it remain readable; their object provenance is `unknown`.

```json
{
  "scene_metadata": {
    "schema_version": 1,
    "objects": {
      "east_gate": {
        "basis": "organizer_confirmed",
        "source": "Organizer site review"
      }
    },
    "fields": {
      "east_gate": {
        "width_m": {
          "basis": "measured",
          "source": "Tape measurement supplied by the organizer",
          "recorded_at": "2026-10-11T10:00:00+06:00"
        }
      }
    }
  }
}
```

The example above is the contents of the `extensions` object. Supported bases are
`unknown`, `assumed`, `imported`, `organizer_confirmed`, and `measured`. Measured fields
require a supplied source, but this does not independently verify the measurement.
Object/field references must exist. Metadata is preserved through existing venue JSON
storage/import/export; this feature adds no provenance editing UI or write endpoint.

## Spatial facts and limits

Every free-space component above the numerical area tolerance of `1e-9 m2` is inspected,
including small isolated regions. An exit is geometrically available when it is not blocked and at least half
its polygon lies in free space, consistent with the existing exit-overlap check.
Declared exit width is exposed separately; it is not a computed clear opening width.

Stairs connect their landing components in the supplied `from_floor` → `to_floor`
direction. Connectivity traversal handles long chains and cycles. It does not infer
reverse travel or change the simulator's simplified stair behavior.

Each zone reports its total headcount, usable/excluded area, reachable/unreachable area,
and a part per contacted free-space component. Reachability can be `reachable`,
`partially_reachable`, `unreachable`, or `unplaced`. A zone touching one accessible
component must not conceal another trapped component. Area fractions do not establish
how many people occupy each component; no new headcount allocation is invented.
`placement` separately identifies `fully_placed`, `partially_placed`, or `unplaced` demand.
Reachability describes the usable portion, not people in excluded/unassessed areas;
occupied zones with excluded area also receive an explicit finding.

Routes use a polygon visibility graph containing boundary vertices and representative
zone, exit, and stair points. Distances are geometric path lengths to exit-area anchors,
plus supplied stair lengths. They are not straight lines through obstacles, evacuation
times, capacity estimates, or maximum travel distances for everyone in a zone.

Point clearance is the distance from the reported representative point to its free-space
boundary. Exit obstacle distance is the distance between the exit polygon and the nearest
obstacle, or `null` when no obstacle exists. Neither is minimum corridor width or clearance
along a full route. Visibility paths permit contact with boundaries and have no body-radius
constraint; zero-width geometric paths are not proof of pedestrian feasibility.

Route work is bounded to 256 nodes per component and 80,000 total visibility checks.
If either budget is exceeded, route computation is withheld for the entire scene;
connectivity/areas still return. Distances remain `null`, with a `not_computed` reason.
`routes_computed` indicates whether the graph was built, not whether every requested
route exists. A topology-reachable region without a graph path reports `not_computed`,
not an invented distance or a changed connectivity verdict.

## Handoff to Person 3

Use `scene_snapshot(venue, project_id=..., version=...)` and
`inspect_scene(venue, project_id=..., version=..., include_routes=...)` from
`api.core.scene` for internal callers, or the HTTP endpoints for external consumers.
Contracts live in `api.models.scene` and are registered in `scripts/export_schemas.py`.
The endpoints also expose their response schemas through `/api/openapi.json`.

For grounded questions, inspect zone parts and their reachable exit IDs rather than
guessing connections from raw coordinates. Compare source identities before combining
facts with another scene or run. Further integration into agent tools and the frontend
is Person 3's work; existing generated web types need regeneration when that integration
starts.

## Test procedure for the next step

For prerequisites, the requirement-by-requirement matrix, manual Swagger examples, and
the live editor/simulator consistency check, use [P2_01_TESTING.md](P2_01_TESTING.md).

Run from `nebius/` on the configured M1. The source mount below uses the new API code
with the existing image's installed dependencies; no image rebuild or AI key is needed
for these isolated tests. `uv run` downloads locked development tools inside the container
if they are absent; that initial setup needs network access.

```bash
docker run --rm --platform linux/arm64 \
  -w /app/api \
  -v "$PWD/api:/app/api:ro" \
  showtime-api:latest \
  uv run --frozen pytest -q --basetemp=/tmp/showtime-scene-tests \
  tests/test_scene.py tests/test_scene_api.py \
  tests/test_venue_core.py tests/test_api.py tests/test_persistence.py
```

Prepared acceptance cases cover analytical areas/distances, wall partitions and gaps,
partially trapped zones, overlapping obstacles and holes, complete obstruction,
unplaced demand, directed stair chains/cycles, invalid geometry/provenance, round trips,
immutability, deterministic identity, route budgets, existing templates, API errors,
historical versions, edits/undo, and OpenAPI response schemas. These tests have not yet
been executed for this implementation.

To inspect through the running app after testing, rebuild with `make m1-test-up`, open
<http://127.0.0.1:8000/api/docs>, create/select a project, and call the scene endpoints.
Blocking the only exit with `allow_new_errors=true` should change reachability while
retaining demand. Query the earlier version to inspect the original facts.
