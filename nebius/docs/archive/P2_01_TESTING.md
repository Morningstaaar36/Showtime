# P2-01 — complete M1 test guide

This guide explains how to test the current implementation. The user reported all 29
scene unit/API cases passing, and the synthetic room's live scene endpoints were checked.
The sample and unit fixture were subsequently corrected for the existing placement-density
limit. The corrected scene suite and existing regressions passed during P2-02 verification
on native M1 Python 3.12. The live simulation source-consistency check remains pending.

Use a checkout containing the P2-01 scene inspection feature and the matching sample below.

## 1. Prerequisites

- An Apple Silicon Mac and the existing Docker Desktop installation, running.
- The project at `/Users/ridhwanasif/Downloads/Nebius/Showtime/nebius`.
- Host `python3` for the launcher; dependencies run inside Docker.
- Docker has the memory allocated for the existing M1 profile (start with at least 4 GB
  as documented in [M1_TEST_SETUP.md](M1_TEST_SETUP.md)). Use small crowds for the live check.
- Network access for initial image builds and missing locked development dependencies.
- Ports 8000 and 5173 available for the live app checks. Isolated automated tests do not
  need these ports or a running app.

No OpenRouter, Nebius, or Tavily key is needed. Automated tests use fake providers and
temporary databases. They do not run crowd simulations. The final live consistency check
does use the existing real local Docker simulator.

```bash
cd /Users/ridhwanasif/Downloads/Nebius/Showtime/nebius
python3 --version
docker info
docker image inspect showtime-api:latest --format '{{.Architecture}}'
```

The API image should be `arm64`. If it is missing, build/start with `make m1-test-up`.

## 2. Run the P2-01 tests first

```bash
mkdir -p cache/uv-tests
docker run --rm --platform linux/arm64 \
  -w /app/api \
  -v "$PWD/api:/app/api:ro" \
  -v "$PWD/cache/uv-tests:/root/.cache/uv" \
  showtime-api:latest \
  uv run --frozen pytest -v --tb=short \
  --basetemp=/tmp/showtime-scene-tests \
  tests/test_scene.py tests/test_scene_api.py
```

The API source mount includes the new feature even if the image was built earlier. The
ignored UV cache avoids redownloading development packages on every invocation. The
first invocation may download them; wait for the pytest output before interpreting the
result. `--basetemp` keeps test databases/files in the disposable container.

Pass condition: every collected case is `PASSED`, no collection errors or failures, and
the process exits with code zero. Test names make it clear which requirement failed.

For one requirement, add `-k` before the test filenames, for example:

```text
-k 'split_occupied_zone'
-k 'provenance'
-k 'route_budget'
-k 'edit_and_historical_version'
```

These are pytest filters, not standalone shell commands. Remove the filter to run all cases.

## 3. Requirement-by-requirement acceptance

Tests below are in `api/tests/test_scene.py`, unless marked **API** (in
`api/tests/test_scene_api.py`). The listed outcomes are expected, not measured results.

| Requirement | Test / procedure | Expected result |
| --- | --- | --- |
| Full canonical geometry is preserved | `test_existing_templates_keep_full_geometry_and_ids`; `test_provenance_hash_and_lossless_snapshot` | Snapshot venue equals original JSON, including all template geometry and optional fields; round trip preserves it. |
| Object IDs remain usable and unambiguous | Template test; `test_invalid_geometry_is_explicitly_rejected[duplicate]` | All original IDs appear once; duplicates raise an explicit error. Empty-ID rejection can also be checked with manual JSON below. |
| Units are explicit | Manual `/scene` and `/scene-facts`; response schema tests | Coordinates/elevations/distances `m`, area `m2`, time `s`, coordinate system `local_cartesian`. |
| Provenance defaults honestly | `test_provenance_hash_and_lossless_snapshot` | Existing objects without metadata have `unknown` provenance. |
| Field provenance survives the snapshot | Same provenance test | Exit-width source/date/basis are available under the matching object and field; original venue JSON remains unchanged. |
| Invalid provenance is rejected | `test_invalid_provenance_rejected` | Unknown objects/fields and measured values without a source are rejected. Bad timestamp format can be checked manually. |
| Complete scene identity and layout identity are distinct | Provenance test | Metadata-only changes alter `scene_hash` while retaining the existing `venue_hash`. |
| Determinism and read-only inspection | `test_inspection_is_deterministic_and_does_not_mutate_scene` | Repeated inspection produces equal facts and leaves source JSON/hash unchanged. |
| Usable area is calculated | `test_room_area_route_and_clearance` | The empty 10 × 8 m room has 80 m2 usable area. |
| Overlapping obstacles are counted once; holes survive | `test_overlapping_obstacles_are_subtracted_once_and_holes_retained` | Obstacle union is 12 m2; usable area is 68 m2; component geometry retains its hole. |
| Walls disconnect areas; gaps restore access | `test_partition_and_gap` | Full partition gives two components and no route for the left zone; a gap restores connectivity and produces a detour. |
| Blocked exits do not disappear from the evidence | `test_blocked_exit_retains_demand_and_marks_unreachable` | Exit is unavailable, route distance is `null`, and zone headcount stays 20. |
| Split zones do not conceal trapped portions | `test_split_occupied_zone_does_not_hide_trapped_portion` | 16 m2 usable zone area: 8 reachable, 8 unreachable; another 8 excluded; explicit partial-reachability finding. No invented allocation of people. |
| Outside/obstructed demand remains visible | `test_zone_outside_scene_is_unplaced_not_zero_demand`; `test_partial_zone_placement_is_explicit`; `test_complete_floor_obstruction_returns_empty_facts` | Unplaced or partially placed labels, excluded area, and headcounts remain visible even when geometry provides no usable placement. |
| Stair connectivity respects supplied direction | `test_stairs_do_not_implicitly_enable_upward_travel` | A downward stair does not provide an implied upward escape route. |
| Stair chains/cycles are handled | `test_directed_stairs_support_long_chains_and_cycles` | Long directed chain reaches the exit; a cycle terminates; representative route length is approximately 28.79 m in this fixture. |
| Geometric route lengths are calculated | Room and partition/gap tests | Empty-room representative-point route is approximately 7.79 m; a blocking obstacle with a gap requires a longer route. |
| Point clearance and obstacle distance have honest meanings | Room test; manual inspection of a wall/obstacle | Room representative-point clearance is approximately 2 m; no obstacles gives `null` exit-obstacle distance. Distance is not full-route clearance or a guaranteed opening width. |
| Route computation is bounded | `test_route_budget_does_not_erase_connectivity` | Node/check budgets produce `not_computed` with `null` distance while preserving connectivity. Tests lower limits deliberately rather than create huge scenes. |
| Routes can be omitted explicitly | `test_routes_can_be_disabled`; **API** `test_no_routes_and_response_schemas` | `include_routes=false` returns areas/connectivity, with `routes_disabled` and no invented distance. |
| Endpoints return typed, compatible responses | **API** `test_scene_endpoints` | Both return 200 and equal source identities; responses validate against their Pydantic contracts. |
| Edits change identity; history remains inspectable | **API** `test_edit_and_historical_version` | Blocking an exit changes version/hash and reachability. `version=1` reproduces original facts. Undo creates version 3 with the original scene hash and zone facts. |
| API errors are explicit | **API** `test_scene_unknown_project_version_and_invalid_query`; `test_invalid_polygon_is_not_repaired_by_scene_endpoint` | Unknown project/version: 404. Version zero: 422. Self-intersecting scene: 422 `invalid_scene`, with issues rather than silently repaired facts. |
| Non-finite/malformed geometry is rejected | Parameterized invalid-geometry test | NaN coordinates, unknown stair floors, and short stair polygons raise explicit inspection errors. NaN is tested in Python because it is not valid standard JSON. |
| Response schemas are available | **API** `test_no_routes_and_response_schemas` | `/api/openapi.json` includes `SceneSnapshot` and `SceneFacts`. |
| Existing project features remain compatible | Regression command in section 4 | Venue patches, project lifecycle, persistence, and API cases still pass. |
| Editor/snapshot/simulator use the same saved geometry | Live procedure in section 7 | Saved version, snapshot JSON, stored run venue JSON, and request venue hash agree for a baseline run of that exact version. |

API tests exercise FastAPI in-process, not a Docker-deployed web server. Sections 5–7
check that deployment and the real simulator too. Unit fixtures establish software
behavior under known inputs; they do not validate crowd physics against real events.

## 4. Run relevant regressions

After the P2-01 cases pass, run this bounded regression set using the same mounts:

```bash
docker run --rm --platform linux/arm64 \
  -w /app/api \
  -v "$PWD/api:/app/api:ro" \
  -v "$PWD/cache/uv-tests:/root/.cache/uv" \
  showtime-api:latest \
  uv run --frozen pytest -v --tb=short \
  --basetemp=/tmp/showtime-scene-regression \
  tests/test_venue_core.py tests/test_api.py tests/test_persistence.py tests/test_redteam.py
```

The red-team tests use fake providers; this checks compatibility, not live AI quality.

## 5. Rebuild the live application

```bash
make m1-test-up
make m1-test-status
```

Use `up`, not just `start`: the running API image needs the new source. Open
<http://127.0.0.1:8000/api/docs> for Swagger and <http://localhost:5173> for the editor.
Missing AI credentials do not block scene inspection. The two new GET endpoints should
appear in Swagger; if absent, the API is still running old code.

## 6. Manual API demonstration

### A. Create a known room

From `nebius/`, you can submit the supplied JSON file directly:

```bash
curl -X POST 'http://127.0.0.1:8000/api/v1/projects' \
  -H 'Content-Type: application/json' \
  --data-binary @docs/examples/p2-01-room-request.json
```

In Swagger, expand `POST /api/v1/projects`, click **Try it out**, paste the following,
and execute. This is synthetic test geometry, not a measured venue.

```json
{
  "name": "P2-01 manual test",
  "venue": {
    "venue_id": "manual_room",
    "name": "P2-01 manual test",
    "mode": "indoor",
    "floors": [{
      "floor_id": "F0",
      "walkable": [[0,0],[10,0],[10,8],[0,8]],
      "obstacles": [],
      "exits": [{
        "id": "E1", "polygon": [[9.6,3],[9.98,3],[9.98,5],[9.6,5]], "width_m": 2
      }],
      "zones": [{
        "id": "Z1", "polygon": [[1,2],[3,2],[3,6],[1,6]], "people": 20
      }]
    }]
  }
}
```

Expected: HTTP 201. Copy the returned project `id`, such as `p_...`. The service replaces
the input venue ID with that project ID; use the returned ID in subsequent paths.

### B. Inspect the snapshot and facts

Call `/projects/{id}/scene`, `/projects/{id}/scene-facts`, and the existing
`/projects/{id}` endpoint. Check:

- Snapshot `venue` equals existing project response `version.venue`.
- Both new responses refer to version 1 and have identical `identity` values.
- IDs include `F0`, `E1`, and `Z1`; provenance is unknown; units are explicit.
- Facts show one component, 80 m2 usable floor, headcount 20, full placement, and reachable `E1`.
- The starting zone has 8 m2 usable area (2.5 people/m2), within the app's placement limit.
- Zone part route is `computed`, approximately 7.79 m; point clearance is approximately 2 m.
- Exit-obstacle distance is `null` because there are no obstacles.

Repeat facts without editing: it should be identical. Add `include_routes=false`: areas
and connectivity stay the same, while the route becomes `not_computed` / `routes_disabled`.

### C. Block the exit and inspect history

Call `POST /projects/{id}/patch` with:

```json
{
  "patch": {"ops": [{"op": "block_exit", "exit_id": "E1"}]},
  "allow_new_errors": true,
  "message": "P2-01 blocked-exit test"
}
```

Expected: patch HTTP 200. Current facts show version 2, a different scene hash, blocked
`E1`, unreachable `Z1`, `null` route distance, and the same headcount 20. Inspection
returns 200 with findings; it does not invent a passing simulation.

Query facts with `version=1`: original reachable facts return. Call `POST /projects/{id}/undo`:
current version becomes 3 with the original scene hash and restored reachability.

### D. Verify a partition and a gap

After undo, call the patch endpoint with:

```json
{
  "patch": {"ops": [{
    "op": "add_obstacle", "floor_id": "F0", "id": "W1", "kind": "wall",
    "polygon": [[4,0],[6,0],[6,8],[4,8]]
  }]},
  "allow_new_errors": true
}
```

Expected: two components, floor usable area 64 m2, left zone unreachable, right exit still
available. Then patch with `{"patch":{"ops":[{"op":"move","target":"W1","dx":0,"dy":1}]},"allow_new_errors":true}`.
The shifted wall leaves a bottom gap; expected: one connected component, usable area
66 m2, reachable zone, and a longer route than the empty-room path. The portion outside
the floor is not subtracted from usable area.

For a split-zone case, create another project using the base room JSON with the full
partition and change the zone polygon to `[[2,2],[8,2],[8,6],[2,6]]`. Expected: partial
reachability, 8 m2 reachable, 8 m2 unreachable, 8 m2 excluded, and headcount still 20.

### E. Check provenance and invalid inputs

Create another copy of the room with an `extensions` object containing:

```json
{
  "scene_metadata": {
    "fields": {"E1": {"width_m": {
      "basis": "assumed", "source": "Synthetic test value"
    }}}
  }
}
```

The exit object's width provenance should show `assumed` and the supplied source.
This tests metadata storage, not measurement validity. To test `measured`, supply a
clearly synthetic source and valid ISO timestamp; then repeat without a source and expect
inspection HTTP 422. Existing project creation may accept metadata before inspection
validates it, so check the scene GET response, not only creation.

Likewise, create copies with a duplicate ID, an empty ID, or self-intersecting floor
`[[0,0],[10,8],[0,8],[10,0]]`; expect `422 invalid_scene` on inspection. Query an unknown
project/version for 404 and `version=0` for 422. A malformed provenance timestamp should
also yield explicit invalid metadata.

## 7. Live editor/simulator consistency check

Use version 1 of the original manual room, without attack/fix/events. This avoids a
later wall or blocked exit changing which geometry is being compared.

1. Open the test project in the existing editor. Confirm its dimensions, door, and zone
   match the saved current snapshot. If you edit anything, fetch the new version and
   use that exact version throughout the remaining comparison. For the simplest run,
   continue with the known historical version 1 via the API.
2. Save the JSON from `GET /projects/{id}/scene?version=1`.
3. Start `POST /api/v1/runs` with the body below:

```json
{
  "project_id": "REPLACE_WITH_PROJECT_ID",
  "version": 1,
  "tier": 2,
  "seed": 10112026,
  "label": "P2-01 source-consistency test"
}
```

4. Expected start response: HTTP 202. Copy the run ID. Poll `GET /runs/{run_id}` until
   it leaves `queued`/`running`. For this small room, acceptance requires `status: ok`,
   `result.provider: docker`, `result.engine: jupedsim`, total agents 20 and remaining 0.
5. Compare `venue_version` with snapshot version 1, and `request.venue_hash` plus
   `result.venue_hash` with the snapshot's `identity.venue_hash`.
6. Call `GET /runs/{run_id}/venue`: its full decoded JSON must equal snapshot `venue`.
   The simulator may transform geometry internally; this check verifies its source input.
7. Open the completed replay in the app and check the same room, exit, and crowd. An old
   version's replay need not match the editor's newer current version; use the recorded
   version consistently.

Repeated identical run requests can reuse saved results. Change the seed if a fresh
execution is required, and record which seed was used. This is a source-consistency and
startup check, not independent scientific validation of crowd behavior.

## 8. What is still outside this test's scope

P2-01 exposes data and inspection APIs. It does not yet make Nemotron/other agents call
the new tools, add scene-facts panels to the UI, enforce staffing/structural constraints,
implement complete operational-plan state, or validate real-world event safety. Those
belong to the subsequent allocated work. Running an existing agent session alone does
not establish that it consumes these new facts.

## 9. Troubleshooting and evidence to keep

| Problem | Action |
| --- | --- |
| Docker unavailable | Start Docker Desktop; check `docker info`. |
| `showtime-api:latest` missing | Run `make m1-test-up`. |
| New routes are 404 / absent from Swagger | Rebuild with `make m1-test-up`; `m1-test-start` alone uses old image code. |
| Development tools are downloading | Wait for pytest; keep the UV cache mount for later invocations. Registry/network failures are setup failures, not failed assertions. |
| A test fails | Keep the test name, assertion/error, and pytest summary. Do not mark the requirement complete. |
| Live simulation cannot start | Check the reported validation issues and selected version; a blocked-exit fixture is deliberately unsuitable for a successful baseline run. |
| Live API/container error | Inspect `make m1-test-logs`. |

Record the tested code revision/local changes, automated output, live project/version/run
IDs, source hashes, and any failing requirement. Full P2-01 acceptance needs both the
automated cases and the live consistency check; syntax/lint passing alone is insufficient.
