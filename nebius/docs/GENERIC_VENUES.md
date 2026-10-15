# Generic venues: any building, several storeys, any event

Status: 2026-10-15, branch `shahraz`. Owner of this document: Person 1 (Shahraz).
Work allocation: [TEAM_TASK_ALLOCATION.md §11](../../TEAM_TASK_ALLOCATION.md#11-generic-venues-push-15-october-2026).

## Why

Organizer feedback (15 Oct): Showtime felt built around its templates. A building picked on the
map arrived as one ground floor with no rooms, the map's floor count was ignored, the designer
stopped at two floors, a hospital behaved like a concert, a march could not be described, and a
multi-storey replay could not be looked at floor by floor. Goal: anyone can model the building
or site they actually have (hospital, school, office tower, rally ground, street march) and
watch any scenario on it.

## The contract (`api/models/venue.py`, additive, schema_version 1)

| Field | Meaning |
| --- | --- |
| `Venue.event_kind` | concert, festival, conference, wedding, rally, march, sports, religious, hospital, school, office, mall, transit, residential, other (or null) |
| `Venue.routes[]` | `Route{id, floor_id, points[≥2], width_m?, label?}`: a march or procession in walking order |
| `Zone.groups[]` | `PeopleGroup{kind: general\|elderly\|child\|wheelchair\|bed\|staff, share}`; shares ≤ 1, the rest are general adults |
| `Zone.pre_movement_s` | seconds before this zone starts moving; null = run default |
| `Zone.route_id` | people walk this route before heading to an exit |

Existing and unchanged: floors (any number), stairs from a higher floor to a lower one, walls as
obstacles of kind `wall`, exits only on floors that have them.

## Patch ops (`plugins/ops_core/structure.py`)

All validated, undoable, offered to the text-edit agent and covered by conformance tests
(`api/tests/test_building_ops.py`).

| Op | Fields |
| --- | --- |
| `add_floor` | `floor_id?, name?, height_m=3.5, copy_walls=true`: on top of the highest floor |
| `remove_floor` | `floor_id`; refuses the last floor; drops its stairs and routes |
| `add_stair` | `id?, from_floor (upper), to_floor (lower), x, y, width_m=1.5, run_m=6, direction` |
| `remove_stair` | `stair_id`; refused when it is someone's last way down |
| `add_wall` | `floor_id, id?, points[≥2], thickness_m=0.2, height_m?` |
| `add_door` | `floor_id, wall_id, x, y, width_m=1.0`: cuts a gap in a wall |
| `add_room` | `floor_id, id?, x, y (south-west corner), width_m, depth_m, door_wall, door_width_m, people?, label?, groups?`; slides inside the outline when it overshoots |
| `set_zone_profile` | `zone_id, groups?, pre_movement_s?, route_id?` (explicit null clears) |
| `add_route` / `remove_route` | `id?, floor_id, points, width_m?, label?` / `route_id` |
| `set_event_kind` | `event_kind` or null |

## API

- `POST /venues/from-map` also takes `levels` (1–40; default the map's `building:levels`, else
  1), `use` (an event kind; default from the building's tags), `interior` (`rooms` | `open`;
  default rooms for hospital, school, office, residential), `floor_height_m` (3.5) and, for open
  areas, `event_kind`. The venue records `extensions.building`.
- `GET /places/at` buildings carry `levels` and `use`.
- `GET /event-kinds`: id, label, description, usual people mix, usual interior;
  `default_pre_movement_s` stays null until a cited value exists.
- Not yet: `surroundings_m` on from-map, `GET /runs/{id}/agents` (see "Remaining").

## The building generator (`api/core/building_gen.py`)

One imported ground floor → N storeys:
- two stair cores searched inside the outline near each end (L-shapes and courtyards move them);
- `rooms`: a corridor along the long axis (2.4 m hospital, 2.0 m school, 1.8 m otherwise),
  rooms either side with doors, grouped into up to three areas per side ("Ward A · 1st floor");
- headcount from IBC 2021 Table 1004.5 occupant load factors when none is given;
- falls back to open floors, then to the ground floor alone, when a layout does not validate,
  and says so in the notes.

## UI

- Map screen: floors stepper (says whether the map listed the number), "Used as", "Inside";
  open areas get "Kind of event". A drawn box used as a building is named after its use.
- Every 3D view of a multi-storey venue has a floor switcher: all floors, spread apart, or one
  floor alone (people and heatmap filtered too).
- Groundwork merged but not yet wired to screens: `web/src/lib/venueOps.ts` (tested payload
  builders for every op above), `web/src/lib/eventKinds.ts` (`useEventKinds` with offline
  fallback), `useUi.editFloor` and the build tools (`wall|door|room|stair|route`),
  `scene/geom.ts` helpers (`stairRun`, `stairProfile`, `wallThickness`, `routeMarks`), and the
  copy under `editor.*` in `en.json`.

## Verified (2026-10-15)

- 4-storey hospital drawn on the map (rooms, 400 people) → AI test with the live model
  (OpenRouter, Nemotron 3 Super): "This plan holds, confirmed by full simulations"; the red
  team chose floor-aware attacks ("East exit blocked during upper floor evacuation", "Surge into
  Ward F on ground floor"); 95% out in 4 min 31 s; one-floor views on the check and plan
  screens.
- Conference hall + third floor + stair + room built by ops: 1,260 people through two chained
  stairs in the hardened Docker sandbox, all out (95% in 2 min 59 s).
- Live text edits: "add a third floor called Gallery", "add a stair from the Gallery down to the
  mezzanine", "a quarter of the audience are wheelchair users and they start moving after 2
  minutes" applied; "a 6 by 4 m office room on the gallery" was refused, now fixed (rooms slide
  inside the outline and walls on the edge are not out of bounds), re-test live.
- Checks: 580 Python tests, 129 web unit tests, 18 sim tests, lint and mypy clean; Playwright 7/7
  with the real model and Docker (the guided journey once failed to start its test on click,
  then passed; see G3-06).

## Remaining (allocated in TEAM_TASK_ALLOCATION.md §11)

- Simulation of people groups, pre-movement and routes; `agents.json` and `GET /runs/{id}/agents`.
- Surroundings around a building (`surroundings_m`).
- Red and blue teams aware of event kind, groups and routes; incidents filtered by kind.
- Editor tools on screen, zone profile inspector, event-kind control, replay colours by people
  kind, routes and stairs drawn, scenario viewer with event markers.
- Known limits: Overpass (OpenStreetMap) servers were all down on 15 Oct, so building clicks
  failed; "Draw an area" works without them. Rooms are a typical plan, not the real interior.
  Rewind is off for multi-floor venues.

## How to try it

```
cd nebius && DOCKER_CONTEXT=default make up       # http://localhost:5173
```
New project → Pick a place → Draw an area (or click a building) → Building (indoor), 4 floors,
Used as Hospital, Rooms and corridors → Build venue → Use this venue → floor switcher top right
→ Test this plan.
